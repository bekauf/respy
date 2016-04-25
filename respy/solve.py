""" This module contains the interface to solve the model.
"""

# project library
from respy.fortran.f2py_library import f2py_create_state_space
from respy.fortran.f2py_library import f2py_solve

from respy.python.solve.solve_auxiliary import start_ambiguity_logging
from respy.python.solve.solve_auxiliary import summarize_ambiguity
from respy.python.solve.solve_auxiliary import logging_solution
from respy.python.solve.solve_auxiliary import check_input
from respy.python.solve.solve_auxiliary import cleanup

from respy.python.shared.shared_auxiliary import dist_class_attributes
from respy.python.shared.shared_auxiliary import dist_model_paras
from respy.python.shared.shared_auxiliary import get_robupy_obj
from respy.python.shared.shared_auxiliary import add_solution
from respy.python.shared.shared_auxiliary import create_draws

from respy.python.solve.solve_python import pyth_solve

from respy.fortran.fortran import fort_solve

''' Main function
'''


def solve(input):
    """ Solve the model
    """
    # Process input
    robupy_obj = get_robupy_obj(input)

    # Checks, cleanup, start logger
    assert check_input(robupy_obj)

    cleanup()

    logging_solution('start')

    # Distribute class attributes
    model_paras, num_periods, edu_start, is_debug, edu_max, delta, \
        is_deterministic, version, num_draws_emax, seed_emax, is_interpolated, \
        is_ambiguous, num_points, is_myopic, min_idx, level, store, \
        tau = \
            dist_class_attributes(robupy_obj,
                'model_paras', 'num_periods', 'edu_start', 'is_debug',
                'edu_max', 'delta', 'is_deterministic', 'version',
                'num_draws_emax', 'seed_emax', 'is_interpolated',
                'is_ambiguous', 'num_points', 'is_myopic', 'min_idx',
                'level', 'store', 'tau')

    # Construct auxiliary objects
    start_ambiguity_logging(is_ambiguous, is_debug)

    # Distribute model parameters
    coeffs_a, coeffs_b, coeffs_edu, coeffs_home, shocks_cov, shocks_cholesky = \
        dist_model_paras(model_paras, is_debug)

    # Get the relevant set of disturbances. These are standard normal draws
    # in the case of an ambiguous world. This function is located outside
    # the actual bare solution algorithm to ease testing across
    # implementations.
    periods_draws_emax = create_draws(num_periods, num_draws_emax, seed_emax,
        is_debug)

    # Collect baseline arguments. These are latter amended to account for
    # each interface.
    base_args = (coeffs_a, coeffs_b, coeffs_edu, coeffs_home, shocks_cov,
        is_deterministic, is_interpolated, num_draws_emax, is_ambiguous,
        num_periods, num_points, is_myopic, edu_start, is_debug,
        edu_max, min_idx, delta, level)

    # Select appropriate interface. The additional preparations for the F2PY
    # interface are required as only explicit shape arguments can be passed
    # into the interface.
    if version == 'FORTRAN':
        args = base_args + (seed_emax, tau)
        solution = fort_solve(*args)
    elif version == 'PYTHON':
        args = base_args + (periods_draws_emax, )
        solution = pyth_solve(*args)
    elif version == 'F2PY':
        args = (num_periods, edu_start, edu_max, min_idx)
        max_states_period = f2py_create_state_space(*args)[3]
        args = base_args + (periods_draws_emax, max_states_period)
        solution = f2py_solve(*args)
    else:
        raise NotImplementedError

    # Attach solution to class instance
    robupy_obj = add_solution(robupy_obj, store, *solution)

    # Summarize optimizations in case of ambiguity
    if is_debug and is_ambiguous and (not is_myopic):
        summarize_ambiguity(robupy_obj)

    # Orderly shutdown of logging capability.
    logging_solution('stop')

    # Finishing
    return robupy_obj

