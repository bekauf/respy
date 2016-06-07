# standard library
import statsmodels.api as sm
from scipy.stats import norm

import numpy as np
import pytest
import scipy

# testing library
from codes.auxiliary import write_interpolation_grid
from codes.random_init import generate_init

from respy.python.solve.solve_auxiliary import logging_solution
from respy.python.solve.solve_auxiliary import get_future_value

from respy.python.estimate.estimate_auxiliary import get_optim_paras
from respy.python.estimate.estimate_auxiliary import dist_optim_paras

from respy.python.shared.shared_auxiliary import dist_class_attributes
from respy.python.shared.shared_auxiliary import dist_model_paras
from respy.python.shared.shared_auxiliary import create_draws

import respy.fortran.f2py_library as fort_lib
import respy.fortran.f2py_debug as fort_debug

from respy.python.solve.solve_auxiliary import pyth_create_state_space
from respy.fortran.f2py_library import f2py_create_state_space

from respy.python.solve.solve_auxiliary import pyth_calculate_payoffs_systematic
from respy.fortran.f2py_library import f2py_calculate_payoffs_systematic

from respy.python.solve.solve_auxiliary import pyth_backward_induction
from respy.fortran.f2py_library import f2py_backward_induction

from respy import solve
from respy import RespyCls
from respy import simulate


@pytest.mark.usefixtures('fresh_directory', 'set_seed')
class TestClass(object):
    """ This class groups together some tests.
    """
    def test_1(self):
        """ Compare the evaluation of the criterion function for the ambiguity
        optimization and the simulated expected future value between the FORTRAN
        and PYTHON implementations. These tests are set up a separate test case
        due to the large setup cost to construct the ingredients for the interface.
        """
        # Generate constraint periods
        constraints = dict()
        constraints['version'] = 'PYTHON'

        # Generate random initialization file
        generate_init(constraints)

        # Perform toolbox actions
        respy_obj = RespyCls('test.respy.ini')

        respy_obj = solve(respy_obj)

        # Extract class attributes
        periods_payoffs_systematic, states_number_period, mapping_state_idx, \
        periods_emax, num_periods, states_all, num_draws_emax, edu_start, \
        edu_max, delta, model_paras, is_debug = \
            dist_class_attributes(respy_obj,
                'periods_payoffs_systematic', 'states_number_period',
                'mapping_state_idx', 'periods_emax', 'num_periods',
                'states_all', 'num_draws_emax', 'edu_start', 'edu_max',
                'delta', 'model_paras', 'is_debug')

        # Auxiliary objects
        shocks_cholesky = dist_model_paras(model_paras, is_debug)[-1]

        # Sample draws
        draws_standard = np.random.multivariate_normal(np.zeros(4),
                            np.identity(4), (num_draws_emax,))

        # Sampling of random period and admissible state index
        period = np.random.choice(range(num_periods))
        k = np.random.choice(range(states_number_period[period]))

        # Select systematic payoffs
        payoffs_systematic = periods_payoffs_systematic[period, k, :]

        # Evaluation of simulated expected future values
        args = (num_periods, num_draws_emax, period, k, draws_standard,
            payoffs_systematic, edu_max, edu_start, periods_emax, states_all,
            mapping_state_idx, delta, shocks_cholesky)

        py = get_future_value(*args)
        f90 = fort_debug.wrapper_get_future_value(*args)

        np.testing.assert_allclose(py, f90, rtol=1e-05, atol=1e-06)

    def test_2(self):
        """ Compare results between FORTRAN and PYTHON of selected
        hand-crafted functions. In test_97() we test FORTRAN implementations
        against PYTHON intrinsic routines.
        """

        for _ in range(25):

            # Create grid of admissible state space values.
            num_periods = np.random.randint(1, 15)
            edu_start = np.random.randint(1, 5)
            edu_max = edu_start + np.random.randint(1, 5)

            # Prepare interface
            min_idx = min(num_periods, (edu_max - edu_start + 1))

            # FORTRAN
            args = (num_periods, edu_start, edu_max, min_idx)
            fort_a, fort_b, fort_c, fort_d = \
                fort_lib.f2py_create_state_space(*args)
            py_a, py_b, py_c, py_d = pyth_create_state_space(*args)

            # Ensure equivalence
            for obj in [[fort_a, py_a], [fort_b, py_b], [fort_c, py_c], [fort_d, py_d]]:
                np.testing.assert_allclose(obj[0], obj[1])

        for _ in range(100):

            # Draw random request for testing purposes
            num_covars = np.random.randint(2, 10)
            num_agents = np.random.randint(100, 1000)
            tiny = np.random.normal(size=num_agents)
            beta = np.random.normal(size=num_covars)

            # Generate sample
            exog = np.random.sample((num_agents, num_covars))
            exog[:, 0] = 1
            endog = np.dot(exog, beta) + tiny

            # Run statsmodels
            results = sm.OLS(endog, exog).fit()

            # Check parameters
            py = results.params
            f90 = fort_debug.wrapper_get_coefficients(endog, exog, num_covars,
                num_agents)
            np.testing.assert_almost_equal(py, f90)

            # Check prediction
            py = results.predict(exog)
            f90 = fort_debug.wrapper_point_predictions(exog, f90, num_agents)
            np.testing.assert_almost_equal(py, f90)

            # Check coefficient of determination and the standard errors.
            py = [results.rsquared, results.bse]
            f90 = fort_debug.wrapper_get_pred_info(endog, f90, exog,
                num_agents, num_covars)
            for i in range(2):
                np.testing.assert_almost_equal(py[i], f90[i])

    def test_3(self):
        """ Compare results between FORTRAN and PYTHON of selected functions. The
        file fortran/debug_interface.f90 provides the F2PY bindings.
        """
        for _ in range(10):

            # Draw random requests for testing purposes.
            num_draws_emax = np.random.randint(2, 1000)
            dim = np.random.randint(1, 6)
            mean = np.random.uniform(-0.5, 0.5, dim)

            matrix = (np.random.multivariate_normal(np.zeros(dim),
                np.identity(dim), dim))
            cov = np.dot(matrix, matrix.T)

            # PDF of normal distribution
            args = np.random.normal(size=3)
            args[-1] **= 2

            f90 = fort_debug.wrapper_normal_pdf(*args)
            py = norm.pdf(*args)

            np.testing.assert_almost_equal(py, f90)

            # Singular Value Decomposition
            py = scipy.linalg.svd(matrix)
            f90 = fort_debug.wrapper_svd(matrix, dim)

            for i in range(3):
                np.testing.assert_allclose(py[i], f90[i], rtol=1e-05, atol=1e-06)

            # Pseudo-Inverse
            py = np.linalg.pinv(matrix)
            f90 = fort_debug.wrapper_pinv(matrix, dim)

            np.testing.assert_allclose(py, f90, rtol=1e-05, atol=1e-06)

            # Inverse
            py = np.linalg.inv(cov)
            f90 = fort_debug.wrapper_inverse(cov, dim)
            np.testing.assert_allclose(py, f90, rtol=1e-05, atol=1e-06)

            # Determinant
            py = np.linalg.det(cov)
            f90 = fort_debug.wrapper_determinant(cov)

            np.testing.assert_allclose(py, f90, rtol=1e-05, atol=1e-06)

            # Trace
            py = np.trace(cov)
            f90 = fort_debug.wrapper_trace(cov)

            np.testing.assert_allclose(py, f90, rtol=1e-05, atol=1e-06)

            # Random normal deviates. This only tests the interface, requires
            # visual inspection in IPYTHON notebook as well.
            fort_debug.wrapper_standard_normal(num_draws_emax)

            # Clipping values below and above bounds.
            num_values = np.random.randint(1, 10000)
            lower_bound = np.random.randn()
            upper_bound = lower_bound + np.random.ranf()
            values = np.random.normal(size=num_values)

            f90 = fort_debug.wrapper_clip_value(values, lower_bound,
                upper_bound, num_values)
            py = np.clip(values, lower_bound, upper_bound)

            np.testing.assert_almost_equal(py, f90)

    def test_5(self):
        """ Testing ten admissible realizations of state space for the first
        three periods.
        """
        # Generate constraint periods
        constraints = dict()
        constraints['periods'] = np.random.randint(3, 5)

        # Generate random initialization file
        generate_init(constraints)

        # Perform toolbox actions
        respy_obj = RespyCls('test.respy.ini')

        respy_obj = solve(respy_obj)

        simulate(respy_obj)

        # Distribute class attributes
        states_number_period = respy_obj.get_attr('states_number_period')

        states_all = respy_obj.get_attr('states_all')

        # The next hard-coded results assume that at least two more
        # years of education are admissible.
        edu_max = respy_obj.get_attr('edu_max')
        edu_start = respy_obj.get_attr('edu_start')

        if edu_max - edu_start < 2:
            return

        # The number of admissible states in the first three periods
        for j, number_period in enumerate([1, 4, 13]):
            assert (states_number_period[j] == number_period)

        # The actual realizations of admissible states in period one
        assert ((states_all[0, 0, :] == [0, 0, 0, 1]).all())

        # The actual realizations of admissible states in period two
        states = [[0, 0, 0, 0], [0, 0, 1, 1], [0, 1, 0, 0]]
        states += [[1, 0, 0, 0]]

        for j, state in enumerate(states):
            assert ((states_all[1, j, :] == state).all())

        # The actual realizations of admissible states in period three
        states = [[0, 0, 0, 0], [0, 0, 1, 0], [0, 0, 1, 1]]
        states += [[0, 0, 2, 1], [0, 1, 0, 0], [0, 1, 1, 0]]
        states += [[0, 1, 1, 1], [0, 2, 0, 0], [1, 0, 0, 0]]
        states += [[1, 0, 1, 0], [1, 0, 1, 1], [1, 1, 0, 0]]
        states += [[2, 0, 0, 0]]

        for j, state in enumerate(states):
            assert ((states_all[2, j, :] == state).all())

    def test_4(self):
        """ Testing whether back-and-forth transformation have no effect.
        """
        # Generate random request
        paras_fixed = np.random.choice([True, False], 26)

        for i in range(10):
            # Create random parameter vector
            base = np.random.uniform(size=26)
            x = base.copy()

            # Apply numerous transformations
            for j in range(10):
                args = dist_optim_paras(x, is_debug=True)
                args += ('all', paras_fixed)
                x = get_optim_paras(*args, is_debug=True)

            # Checks
            np.testing.assert_allclose(base, x)

    def test_5(self):
        """ Testing the core functions of the solution step for the equality
        of results between the PYTHON and FORTRAN implementations.
        """

        # Generate random initialization file
        generate_init()

        # Perform toolbox actions
        respy_obj = RespyCls('test.respy.ini')

        # Ensure that backward induction routines use the same grid for the
        # interpolation.
        write_interpolation_grid('test.respy.ini')

        # Extract class attributes
        num_periods, edu_start, edu_max, min_idx, model_paras, num_draws_emax, \
            seed_emax, is_debug, delta, is_interpolated, num_points_interp, = \
                dist_class_attributes(respy_obj,
                    'num_periods', 'edu_start', 'edu_max', 'min_idx',
                    'model_paras', 'num_draws_emax', 'seed_emax', 'is_debug',
                    'delta', 'is_interpolated', 'num_points_interp')

        # Auxiliary objects
        coeffs_a, coeffs_b, coeffs_edu, coeffs_home, shocks_cholesky = \
            dist_model_paras(model_paras, is_debug)

        # Check the state space creation.
        args = (num_periods, edu_start, edu_max, min_idx)
        pyth = pyth_create_state_space(*args)
        f2py = f2py_create_state_space(*args)
        for i in range(4):
            np.testing.assert_allclose(pyth[i], f2py[i])

        # Carry some results from the state space creation for future use.
        states_all, states_number_period = pyth[:2]
        mapping_state_idx, max_states_period = pyth[2:]

        # Cutting to size
        states_all = states_all[:, :max(states_number_period), :]
        
        # Check calculation of systematic components of payoffs.
        args = (num_periods, states_number_period, states_all, edu_start,
            coeffs_a, coeffs_b, coeffs_edu, coeffs_home, max_states_period)
        pyth = pyth_calculate_payoffs_systematic(*args)
        f2py = f2py_calculate_payoffs_systematic(*args)
        np.testing.assert_allclose(pyth, f2py)

        # Carry some results from the systematic payoff calculation for
        # future use and create the required set of disturbances.
        periods_draws_emax = create_draws(num_periods, num_draws_emax,
            seed_emax, is_debug)

        periods_payoffs_systematic = pyth

        # Check backward induction procedure.
        args = (num_periods, max_states_period, periods_draws_emax,
            num_draws_emax, states_number_period, periods_payoffs_systematic,
            edu_max, edu_start, mapping_state_idx, states_all, delta,
            is_debug, is_interpolated, num_points_interp, shocks_cholesky)

        logging_solution('start')
        pyth = pyth_backward_induction(*args)
        logging_solution('stop')

        f2py = f2py_backward_induction(*args)
        np.testing.assert_allclose(pyth, f2py)
