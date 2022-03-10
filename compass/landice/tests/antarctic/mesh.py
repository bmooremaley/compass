import numpy as np
import netCDF4
import xarray
from matplotlib import pyplot as plt
from shutil import copyfile

from mpas_tools.mesh.creation import build_planar_mesh
from mpas_tools.mesh.conversion import convert, cull
from mpas_tools.planar_hex import make_planar_hex_mesh
from mpas_tools.io import write_netcdf
from mpas_tools.logging import check_call

from compass.step import Step
from compass.model import make_graph_file
from compass.landice.mesh import gridded_flood_fill, \
                                 set_rectangular_geom_points_and_edges, \
                                 set_cell_width, get_dist_to_edge_and_GL


class Mesh(Step):
    """
    A step for creating a mesh and initial condition for Antarctic test cases

    Attributes
    ----------
    mesh_type : str
        The resolution or mesh type of the test case
    """
    def __init__(self, test_case):
        """
        Create the step

        Parameters
        ----------
        test_case : compass.TestCase
            The test case this step belongs to

        mesh_type : str
            The resolution or mesh type of the test case
        """
        super().__init__(test_case=test_case, name='mesh')

        self.add_output_file(filename='graph.info')
        self.add_output_file(filename='Antarctic_1to10km.nc')
        self.add_input_file(
                filename='antarctica_8km_2020_10_20.nc',
                target='antarctica_8km_2020_10_20.nc',
                database='')

    # no setup() method is needed

    def run(self):
        """
        Run this step of the test case
        """
        logger = self.logger
        config = self.config
        section = config['antarctic']

        logger.info('calling build_cell_width')
        cell_width, x1, y1, geom_points, geom_edges, floodFillMask = \
                                                   self.build_cell_width()
        logger.info('calling build_planar_mesh')
        build_planar_mesh(cell_width, x1, y1, geom_points,
                          geom_edges, logger=logger)
        dsMesh = xarray.open_dataset('base_mesh.nc')
        logger.info('culling mesh')
        dsMesh = cull(dsMesh, logger=logger)
        logger.info('converting to MPAS mesh')
        dsMesh = convert(dsMesh, logger=logger)
        logger.info('writing grid_converted.nc')
        write_netcdf(dsMesh, 'grid_converted.nc')
        # If no number of levels specified in config file, use 10
        levels = section.get('levels')
        logger.info('calling create_landice_grid_from_generic_MPAS_grid.py')
        args = ['create_landice_grid_from_generic_MPAS_grid.py',
                '-i', 'grid_converted.nc',
                '-o', 'ais_8km_preCull.nc',
                '-l', levels, '-v', 'glimmer']
        check_call(args, logger=logger)

        # Apply floodFillMask to thickness field to help with culling
        copyfile('antarctica_8km_2020_10_20.nc', 'antarctica_8km_2020_10_20_floodFillMask.nc')
        gg = netCDF4.Dataset('antarctica_8km_2020_10_20_floodFillMask.nc', 'r+')
        gg.variables['thk'][0,:,:] *= floodFillMask
        gg.variables['vx'][0,:,:] *= floodFillMask
        gg.variables['vy'][0,:,:] *= floodFillMask
        gg.close()
        
        # This step uses a subset of the whole Antarctic dataset trimmed to
        # the region around Antarctica, to speed up interpolation.
        # This could also be replaced with the full Antarctic Ice Sheet
        # dataset.
        logger.info('calling interpolate_to_mpasli_grid.py')
        args = ['interpolate_to_mpasli_grid.py', '-s',
                'antarctica_8km_2020_10_20_floodFillMask.nc', '-d',
                'ais_8km_preCull.nc', '-m', 'b', '-t']

        check_call(args, logger=logger)

        # This step is only necessary if you wish to cull a certain
        # distance from the ice margin, within the bounds defined by
        # the GeoJSON file.
        cullDistance = section.get('cull_distance')
        if float(cullDistance) > 0.:
            logger.info('calling define_cullMask.py')
            args = ['define_cullMask.py', '-f',
                    'ais_8km_preCull.nc', '-m'
                    'distance', '-d', cullDistance]

            check_call(args, logger=logger)
        else:
            logger.info('cullDistance <= 0 in config file. '
                        'Will not cull by distance to margin. \n')

        # This step is only necessary because the GeoJSON region
        # is defined by lat-lon.
        logger.info('calling set_lat_lon_fields_in_planar_grid.py')
        args = ['set_lat_lon_fields_in_planar_grid.py', '-f',
                'ais_8km_preCull.nc', '-p', 'ais-bedmap2']

        check_call(args, logger=logger)

        dsMesh = xarray.open_dataset('ais_8km_preCull.nc')
        dsMesh = cull(dsMesh, logger=logger)
        write_netcdf(dsMesh, 'antarctic_culled.nc')

        logger.info('Marking horns for culling')
        args = ['mark_horns_for_culling.py', '-f', 'antarctic_culled.nc']
        check_call(args, logger=logger)

        logger.info('culling and converting')
        dsMesh = xarray.open_dataset('antarctic_culled.nc')
        dsMesh = cull(dsMesh, logger=logger)
        dsMesh = convert(dsMesh, logger=logger)
        write_netcdf(dsMesh, 'antarctic_dehorned.nc')

        logger.info('calling create_landice_grid_from_generic_MPAS_grid.py')
        args = ['create_landice_grid_from_generic_MPAS_grid.py', '-i',
                'antarctic_dehorned.nc', '-o',
                'Antarctic_1to10km.nc', '-l', levels, '-v', 'glimmer',
                '--beta', '--thermal', '--obs', '--diri']

        check_call(args, logger=logger)

        logger.info('calling interpolate_to_mpasli_grid.py')
        args = ['interpolate_to_mpasli_grid.py', '-s',
                'antarctica_8km_2020_10_20.nc',
                '-d', 'Antarctic_1to10km.nc', '-m', 'b']
        check_call(args, logger=logger)

        logger.info('Marking domain boundaries dirichlet')
        args = ['mark_domain_boundaries_dirichlet.py',
                '-f', 'Antarctic_1to10km.nc']
        check_call(args, logger=logger)

        logger.info('calling set_lat_lon_fields_in_planar_grid.py')
        args = ['set_lat_lon_fields_in_planar_grid.py', '-f',
                'Antarctic_1to10km.nc', '-p', 'ais-bedmap2']
        check_call(args, logger=logger)

        logger.info('creating graph.info')
        make_graph_file(mesh_filename='Antarctic_1to10km.nc',
                        graph_filename='graph.info')

    def build_cell_width(self):
        """
        Determine MPAS mesh cell size based on user-defined density function.

        This includes hard-coded definition of the extent of the regional
        mesh and user-defined mesh density functions based on observed flow
        speed and distance to the ice margin. In the future, this function
        and its components will likely be separated into separate generalized
        functions to be reusable by multiple test groups.
        """
        # get needed fields from AIS dataset
        f = netCDF4.Dataset('antarctica_8km_2020_10_20.nc', 'r')
        f.set_auto_mask(False)  # disable masked arrays

        x1 = f.variables['x1'][:]
        y1 = f.variables['y1'][:]
        thk = f.variables['thk'][0, :, :]
        topg = f.variables['topg'][0, :, :]
        vx = f.variables['vx'][0, :, :]
        vy = f.variables['vy'][0, :, :]

        # Define extent of region to mesh.
        # These coords are specific to the Antarctic mesh.
        xx0 = -3333500
        xx1 = 3330500
        yy0 = -3333500
        yy1 = 3330500
        geom_points, geom_edges = set_rectangular_geom_points_and_edges(
                                                           xx0, xx1, yy0, yy1)

        # Remove ice not connected to the ice sheet.
        floodMask = gridded_flood_fill(thk)
        thk[floodMask == 0] = 0.0
        vx[floodMask == 0] = 0.0
        vy[floodMask == 0] = 0.0

        # Calculate distance from each grid point to ice edge
        # and grounding line, for use in cell spacing functions.
        distToEdge, distToGL = get_dist_to_edge_and_GL(self, thk, topg, x1,
                                                       y1, window_size=1.e5)
        # optional - plot distance calculation
        # plt.pcolor(distToEdge/1000.0); plt.colorbar(); plt.show()

        # Set cell widths based on mesh parameters set in config file
        cell_width = set_cell_width(self, section='antarctic', thk=thk,
                                    vx=vx, vy=vy, dist_to_edge=distToEdge,
                                    dist_to_grounding_line=distToGL)
        # plt.pcolor(cell_width); plt.colorbar(); plt.show()

        return (cell_width.astype('float64'), x1.astype('float64'),
                y1.astype('float64'), geom_points, geom_edges, floodMask)
