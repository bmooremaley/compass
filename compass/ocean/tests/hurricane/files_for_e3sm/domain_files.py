import os
from datetime import datetime

from mpas_tools.logging import check_call

from compass.step import Step


class DomainFiles(Step):
    """
    A step for building domain files for meshes tailored to hurricane-induced
    coastal flooding

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
        super().__init__(test_case, name='domain_files')
        self.mesh = test_case.mesh

    def setup(self):
        """
        Set up the step in the work directory, including downloading any
        dependencies.
        """
        super().setup()
        date_stamp = datetime.now().strftime('%Y%m%d')
        self.date_stamp = date_stamp

        fname = 'map_ocn_to_atm_conserve.nc'
        target = os.path.join(self.test_case.steps['forcing_maps'].path, fname)
        self.add_input_file(filename=fname, work_dir_target=target)

        atm_grid = self.config.get('files_for_e3sm', 'atm_grid')
        ocn_grid = self.mesh.mesh_name
        self.add_output_file(
            filename=f'domain.lnd.{atm_grid}_{ocn_grid}.{date_stamp}.nc')
        self.add_output_file(
            filename=f'domain.ocn.{atm_grid}_{ocn_grid}.{date_stamp}.nc')
        self.add_output_file(
            filename=f'domain.ocn.{ocn_grid}.{date_stamp}.nc')

    def run(self):
        """
        Run this step of the test case
        """
        super().run()
        self._domain_files()

    def _domain_files(self):
        """
        Create domain files
        """

        section = self.config['files_for_e3sm']
        domain_files_exe = section.get('domain_files_exe')
        atm_grid = section.get('atm_grid')
        ocn_grid = self.mesh.mesh_name

        logger = self.logger
        logger.info(
            f'Create domain files for {atm_grid}_{ocn_grid} grid pair.'
        )

        args = [
            'python', domain_files_exe,
            '--date-stamp', self.date_stamp,
            '-m', 'map_ocn_to_atm_conserve.nc',
            '-o', ocn_grid,
            '-l', atm_grid,
        ]
        check_call(args, logger)

        logger.info('  Done.')

