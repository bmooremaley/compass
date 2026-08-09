from mpas_tools.logging import check_call
from pyremap import MpasCellMeshDescriptor

from compass.parallel import run_command
from compass.step import Step


class ForcingMaps(Step):
    """
    A step for building mapping files for remapping forcing files
    to a global MPAS-Ocean mesh

    Attributes
    ----------
    mesh : compass.mesh.spherical.SphericalBaseStep
        The base mesh step containing input files to this step
    """

    def __init__(self, test_case):
        """
        Create a new step

        Parameters
        ----------
        test_case : compass.ocean.tests.hurricane.files_for_e3sm.FilesForE3SM
            The test case this step belongs to
        """
        super().__init__(test_case, name='forcing_maps')
        self.mesh = test_case.mesh

    def setup(self):
        """
        Set up the step in the work directory, including downloading any
        dependencies.
        """
        super().setup()

        mesh_path = self.mesh.steps['cull_mesh'].path
        self.add_input_file(filename='mesh.nc', work_dir_target=f'{mesh_path}/culled_mesh.nc')
        self.add_output_file(filename='map_atm_to_ocn_bilinear.nc')
        self.add_output_file(filename='map_atm_to_ocn_conserve.nc')
        self.add_output_file(filename='map_ocn_to_atm_bilinear.nc')
        self.add_output_file(filename='map_ocn_to_atm_conserve.nc')

        self._get_resources()

    def constrain_resources(self, available_resources):
        """
        Constrain ``cpus_per_task`` and ``ntasks`` based on the number of
        cores available to this step

        Parameters
        ----------
        available_resources : dict
            The total number of cores available to the step
        """
        self._get_resources()
        super().constrain_resources(available_resources)

    def run(self):
        """
        Run this step of the test case
        """
        super().run()

        self._scrip_file_gridded()
        self._scrip_file_MPAS()
        self._create_weights('atm', 'ocn', 'bilinear')
        self._create_weights('atm', 'ocn', 'conserve')
        self._create_weights('ocn', 'atm', 'bilinear')
        self._create_weights('ocn', 'atm', 'conserve')

    def _get_resources(self):
        """
        Get resources
        """
        section = self.config['hurricane']
        self.ntasks = section.getint('init_ntasks')
        self.min_tasks = section.getint('init_min_tasks')
        self.openmp_threads = section.getint('init_threads')

    def _scrip_file_gridded(self):
        """
        Create gridded SCRIP file for atm
        """
        logger = self.logger
        grid_name = self.config.get('files_for_e3sm', 'atm_grid')
        logger.info(f'Create gridded SCRIP file for {grid_name} grid')

        grids = {
            'T382': {
                'nlat': 576,
                'nlon': 1152,
                'lat_typ': 'gss',
                'lon_typ': 'grn_ctr',
            },
            'T574': {
                'nlat': 880,
                'nlon': 1760,
                'lat_typ': 'gss',
                'lon_typ': 'grn_ctr',
            },
        }

        nlat, nlon, lat_typ, lon_typ = grids[grid_name].values()
        args = [
            'ncremap',
            '-G', f'latlon={nlat},{nlon}#lat_typ={lat_typ}#lon_typ={lon_typ}',
            '-g', 'atm.scrip.nc',
        ]
        check_call(args, logger)

        logger.info('  Done.')

    def _scrip_file_MPAS(self):
        """
        Create SCRIP file from MPAS mesh file.
        """
        mesh_name = self.mesh.mesh_name
        logger = self.logger
        logger.info(f'Create MPAS SCRIP file for {mesh_name} mesh')

        descriptor = MpasCellMeshDescriptor(
            filename='mesh.nc',
            mesh_name=mesh_name,
        )
        descriptor.to_scrip('ocn.scrip.nc')

        logger.info('  Done.')

    def _create_weights(self, src, tgt, method):
        """
        Create mapping weights file using ESMF_RegridWeightGen
        """
        logger = self.logger
        logger.info(f'Create {src}_to_{tgt} weights file')

        args = [
            'ESMF_RegridWeightGen',
            '--source', f'{src}.scrip.nc',
            '--destination', f'{tgt}.scrip.nc',
            '--weight', f'map_{src}_to_{tgt}_{method}.nc',
            '--method', method,
            '--netcdf4',
            '--ignore_unmapped',
        ]

        run_command(
            args, self.cpus_per_task, self.ntasks,
            self.openmp_threads, self.config, self.logger,
        )

        logger.info('  Done.')
