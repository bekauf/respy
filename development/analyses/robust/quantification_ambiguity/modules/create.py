#!/usr/bin/env python
""" This script attempts to express the ambiguity quantification.
"""

# standard library
from multiprocessing import Pool
from functools import partial

import numpy as np

import argparse
import shutil
import socket
import sys
import os

# module-wide variable
ROBUPY_DIR = os.environ['ROBUPY']
SPEC_DIR = ROBUPY_DIR + '/development/analyses/restud/specifications'

# PYTHONPATH
sys.path.insert(0, ROBUPY_DIR + '/development/analyses/robust/_scripts')
sys.path.insert(0, ROBUPY_DIR + '/development/tests/random')
sys.path.insert(0, ROBUPY_DIR)

# _scripts library
from _auxiliary import float_to_string
from _auxiliary import get_robupy_obj

# project library
from robupy import solve
from robupy import read

# robupy library
from robupy.tests.random_init import print_random_dict
from modules.auxiliary import compile_package

# local library
from auxiliary import distribute_arguments
from auxiliary import store_results


def run(is_debug, ambiguity_level):
    """ Extract expected lifetime value.
    """
    os.chdir('rslts')

    # Auxiliary objects
    name = float_to_string(ambiguity_level)

    # Prepare directory structure
    os.mkdir(name), os.chdir(name)

    # Initialize auxiliary objects
    init_dict['AMBIGUITY']['level'] = ambiguity_level

    # Restrict number of periods for debugging purposes.
    if is_debug:
        init_dict['BASICS']['periods'] = 3

    # Print initialization file for debugging purposes.
    print_random_dict(init_dict)

    # Solve the basic economy
    robupy_obj = solve(get_robupy_obj(init_dict))

    # Get the EMAX for further processing and extract relevant information.
    total_value = robupy_obj.get_attr('periods_emax')[0, 0]

    # Back to root directory
    os.chdir('../../')

    # Finishing
    return total_value


''' Execution of module as script.
'''

if __name__ == '__main__':

    parser = argparse.ArgumentParser(
        description='Assess implications of model misspecification.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument('--grid', action='store', type=float, dest='grid',
        default=[0, 0.01, 2], nargs=3,
        help='input for grid creation: lower, upper, points')

    parser.add_argument('--spec', action='store', type=str, dest='spec',
        default='one', help='baseline specification')

    parser.add_argument('--recompile', action='store_true', default=False,
        dest='is_recompile', help='recompile package')

    parser.add_argument('--debug', action='store_true', dest='is_debug',
        help='only three periods')

    parser.add_argument('--procs', action='store', type=int, dest='num_procs',
         default=1, help='use multiple processors')

    # Cleanup
    os.system('./clean'), os.mkdir('rslts')

    # Distribute attributes
    grid, is_recompile, is_debug, num_procs, spec = \
        distribute_arguments(parser)

    # Read the baseline specification and obtain the initialization dictionary.
    shutil.copy(SPEC_DIR + '/data_' + spec + '.robupy.ini', 'model.robupy.ini')
    init_dict = read('model.robupy.ini').get_attr('init_dict')
    os.unlink('model.robupy.ini')

    # Ensure that fast version of package is available. This is a little more
    # complicated than usual as the compiler on acropolis does use other
    # debugging flags and thus no debugging is requested.
    if is_recompile:
        if 'acropolis' in socket.gethostname():
            compile_package('--fortran', True)
        else:
            compile_package('--fortran --debug', True)

    # Here I need the grid creation for the mp processing.
    start, end, num = grid
    levels = np.linspace(start, end, num)

    # Set up pool for processors for parallel execution.
    process_tasks = partial(run, is_debug)
    rslts = Pool(num_procs).map(process_tasks, levels)

    # Restructure return arguments for better interpretability and further
    # processing. Add the baseline number.
    rslt = dict()
    for i, level in enumerate(levels):
        rslt[level] = rslts[i]

    # Store for further processing
    store_results(rslt)
