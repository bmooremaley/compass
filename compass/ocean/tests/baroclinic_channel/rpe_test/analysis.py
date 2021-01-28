import os
import numpy as np
from netCDF4 import Dataset
import matplotlib.pyplot as plt
import cmocean

from compass.testcase import get_step_default
from compass.io import symlink, add_input_file, add_output_file


def collect(resolution):
    """
    Get a dictionary of step properties

    Parameters
    ----------
    resolution : {'1km', '4km', '10km'}
        The name of the resolution to run at

    Returns
    -------
    step : dict
        A dictionary of properties of this step
    """
    step = get_step_default(__name__)
    step['resolution'] = resolution

    step['cores'] = 1
    step['min_cores'] = 1
    # Maximum allowed memory and disk usage in MB
    step['max_memory'] = 8000
    step['max_disk'] = 8000

    return step


def setup(step, config):
    """
    Set up the test case in the work directory, including downloading any
    dependencies

    Parameters
    ----------
    step : dict
        A dictionary of properties of this step from the ``collect()`` function

    config : configparser.ConfigParser
        Configuration options for this testcase, a combination of the defaults
        for the machine, core, configuration and testcase
    """
    resolution = step['resolution']
    step_dir = step['work_dir']

    for index, nu in enumerate([1, 5, 10, 20, 200]):
        add_input_file(
            step, filename='output_{}.nc'.format(index+1),
            target='../rpe_test_{}_nu_{}/output.nc'.format(index+1, nu))

    add_output_file(
        step, filename='sections_baroclinic_channel_{}.png'.format(resolution))


def run(step, test_suite, config, logger):
    """
    Run this step of the testcase

    Parameters
    ----------
    step : dict
        A dictionary of properties of this step from the ``collect()``
        function, with modifications from the ``setup()`` function.

    test_suite : dict
        A dictionary of properties of the test suite

    config : configparser.ConfigParser
        Configuration options for this testcase, a combination of the defaults
        for the machine, core and configuration

    logger : logging.Logger
        A logger for output from the step
    """
    filename = step['outputs'][0]
    section = config['baroclinic_channel']
    nx = section.getint('nx')
    ny = section.getint('ny')
    _plot(nx, ny, filename)


def _plot(nx, ny, filename):
    """
    Plot section of the baroclinic channel at different viscosities

    Parameters
    ----------
    nx : int
        The number of cells in the x direction

    ny : int
        The number of cells in the y direction (before culling)
    """

    plt.switch_backend('Agg')

    nRow = 1
    nCol = 5
    nu = ['1', '5', '10', '100', '200']
    iTime = [0]
    time = ['20']

    fig, axs = plt.subplots(nRow, nCol, figsize=(
        2.1 * nCol, 5.0 * nRow), constrained_layout=True)

    for iCol in range(nCol):
        for iRow in range(nRow):
            ncfile = Dataset('output_{}.nc'.format(iCol + 1), 'r')
            var = ncfile.variables['temperature']
            var1 = np.reshape(var[iTime[iRow], :, 0], [ny, nx])
            # flip in y-dir
            var = np.flipud(var1)

            # Every other row in y needs to average two neighbors in x on
            # planar hex mesh
            var_avg = var
            for j in range(0, ny, 2):
                for i in range(1, nx - 2):
                    var_avg[j, i] = (var[j, i + 1] + var[j, i]) / 2.0

            if nRow == 1:
                ax = axs[iCol]
            else:
                ax = axs[iRow, iCol]
            dis = ax.imshow(
                var_avg,
                extent=[0, 160, 0, 500],
                cmap='cmo.thermal',
                vmin=11.8,
                vmax=13.0)
            ax.set_title("day {}, $\\nu_h=${}".format(time[iRow], nu[iCol]))
            ax.set_xticks(np.arange(0, 161, step=40))
            ax.set_yticks(np.arange(0, 501, step=50))

            if iRow == nRow - 1:
                ax.set_xlabel('x, km')
            if iCol == 0:
                ax.set_ylabel('y, km')
            if iCol == nCol - 1:
                if nRow == 1:
                    fig.colorbar(dis, ax=axs[nCol - 1], aspect=40)
                else:
                    fig.colorbar(dis, ax=axs[iRow, nCol - 1], aspect=40)
            ncfile.close()

    plt.savefig(filename)
