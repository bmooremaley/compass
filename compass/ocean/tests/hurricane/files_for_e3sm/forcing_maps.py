import os
import pathlib

import numpy as np
import xarray as xr
from mpas_tools.cime.constants import constants
from mpas_tools.io import write_netcdf
from mpas_tools.logging import check_call
from pyremap import MpasCellMeshDescriptor

from compass.io import symlink
from compass.parallel import run_command
from compass.step import Step


class ForcingMaps(Step):
    """
    A step for building mapping files for remapping forcing files
    to a global MPAS-Ocean mesh

    Attributes
    ----------
    base_mesh_step : compass.mesh.spherical.SphericalBaseStep
        The base mesh step containing input files to this step
    """

    def __init__(self, test_case, mesh):
        """
        Create a new step

        Parameters
        ----------
        test_case : compass.ocean.tests.global_ocean.mesh.Mesh
            The test case this step belongs to

        mesh : compass.mesh
            Mesh step
        """
        super().__init__(test_case, name='forcing_maps')
        self.mesh = mesh

    def setup(self):
        """
        Set up the step in the work directory, including downloading any
        dependencies.
        """
        super().setup()
    
        mesh_name = self.mesh.name
        mesh_path = self.mesh.steps['cull_mesh'].path
        CFSR_LR = f'CFSR{_resolution(361, 720)}'
        CFSR_HR = f'CFSR{_resolution(880, 1760)}'
        self.add_input_file(filename='mesh.nc', work_dir_target=f'{mesh_path}/culled_mesh.nc')
        self.add_output_file(filename=f'{CFSR_LR}.scrip.nc')
        self.add_output_file(filename=f'{CFSR_HR}.scrip.nc')
        self.add_output_file(filename=f'{mesh_name}.scrip.nc')
        self.add_output_file(filename=f"map_{CFSR_LR}_to_{CFSR_HR}_bilinear.nc")
        self.add_output_file(filename=f"map_{CFSR_HR}_to_{mesh_name}_bilinear.nc")

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

        CFSR_LR = f'CFSR{_resolution(361, 720)}'
        CFSR_HR = f'CFSR{_resolution(880, 1760)}'
        self._scrip_file_gridded('CFSR', 361, 720, 'gss', 'grn_ctr') # Check this
        self._scrip_file_gridded('CFSR', 880, 1760, 'gss', 'grn_ctr')
        self._scrip_file_MPAS()
        self._create_weights(CFSR_LR, CFSR_HR)
        self._create_weights(CFSR_HR, self.mesh.name)
    
    def _get_resources(self):
        """
        Get resources
        """
        section = self.config['hurricane']
        self.ntasks = section.getint('init_ntasks')
        self.min_tasks = section.getint('init_min_tasks')
        self.openmp_threads = section.getint('init_threads')
    
    def _scrip_file_gridded(self, name, nlat, nlon, lat_typ, lon_typ):
        """
        Create gridded SCRIP file
        """
        resolution = _resolution(nlat, nlon)
        grid_name = f'{name} {resolution} grid'
        logger = self.logger
        logger.info(f'Create gridded SCRIP file for {grid_name}')

        args = [
            'ncremap', '-G',
            f"ttl='{grid_name}'" + \
            f'#latlon={nlat},{nlon}#lat_typ={lat_typ}#lon_typ={lon_typ}',
            '-g', f'{name}{resolution}.scrip.nc',
        ]
        check_call(args, logger)

        logger.info('  Done.')

    def _scrip_file_MPAS(self):
        """
        Create SCRIP file from MPAS mesh file.
        """
        mesh_name = self.mesh.name
        logger = self.logger
        logger.info(f'Create MPAS SCRIP file for {mesh_name}')

        descriptor = MpasCellMeshDescriptor(
            filename='base_mesh.nc',
            mesh_name=mesh_name,
        )
        descriptor.to_scrip(f'{mesh_name}.scrip.nc')

        logger.info('  Done.')

    def _create_weights(self, src, tgt):
        """
        Create mapping weights file using ESMF_RegridWeightGen
        """
        logger = self.logger
        logger.info(f'Create {src}_to_{tgt} weights file')

        args = [
            'ESMF_RegridWeightGen',
            '--source', f'{src}.scrip.nc',
            '--destination', f'{tgt}.scrip.nc',
            '--weight', f'map_{src}_to_{tgt}_bilinear.nc',
            '--method', 'bilinear',
            '--netcdf4',
            '--ignore_unmapped',
        ]

        run_command(
            args, self.cpus_per_task, self.ntasks,
            self.openmp_threads, self.config, self.logger,
        )

        logger.info('  Done.')


def _resolution(nlat, nlon):
    """
    Resolution string constructor
    """

    # Get resolution
    res = [str(round(N / n, 1)) for N, n in zip([180, 360], [nlat, nlon])]
    res = f"{'x'.join(res)}degree"

    return res