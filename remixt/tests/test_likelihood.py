import sys
import os
import unittest
import copy
import itertools
import numpy as np
import pandas as pd
import scipy
import scipy.optimize
from scipy.special import gammaln, betaln
import statsmodels.tools.numdiff

import remixt.simulations.simple as sim_simple
import remixt.simulations.experiment as sim_experiment
import remixt.likelihood as likelihood
import remixt.tests.unopt.likelihood as likelihood_unopt
import remixt.likelihood
import remixt.paramlearn


np.random.seed(2014)


def assert_grad_correct(func, grad, x0, *args, **kwargs):
    """ Assert correct gradiant compared to finite difference approximation
    """

    analytic_fprime = grad(x0, *args)
    approx_fprime = statsmodels.tools.numdiff.approx_fprime_cs(x0, func, args=args)

    np.testing.assert_almost_equal(analytic_fprime, approx_fprime, 5)


class likelihood_unittest(unittest.TestCase):

    def generate_simple_data(self):

        N = 100
        M = 3
        r = np.array([75, 75, 75])

        l = np.random.uniform(low=100000, high=1000000, size=N)
        phi = np.random.uniform(low=0.2, high=0.4, size=N)
        p = np.vstack([phi, phi, np.ones(phi.shape)]).T

        cn = sim_simple.generate_cn(N, M, 2.0, 0.5, 0.5, 2)
        h = np.random.uniform(low=0.5, high=2.0, size=M)

        likelihood_model = likelihood.ReadCountLikelihood()
        likelihood_model.h = h
        likelihood_model.phi = phi

        mu = likelihood_model.expected_read_count(l, cn)

        nb_p = mu / (r + mu)

        x = np.array([np.random.negative_binomial(r, 1.-a) for a in nb_p])
        x = x.reshape(nb_p.shape)

        return cn, h, l, phi, r, x


    def generate_count_data(self):

        N = 100
        r = 75.

        mu = np.random.uniform(low=100000, high=1000000, size=N)

        nb_p = mu / (r + mu)
        x = np.random.negative_binomial(r, 1.-nb_p)

        return mu, x


    def generate_allele_data(self):

        N = 100

        p = np.random.uniform(low=0.01, high=0.99, size=N)
        x = np.random.uniform(low=10000, high=50000, size=(N,2))

        return p, x


    def test_expected_read_count_opt(self):

        cn, h, l, phi, r, x = self.generate_simple_data()

        emission = likelihood_unopt.ReadCountLikelihood()
        emission.h = h
        emission.phi = phi

        unopt = emission.expected_read_count_unopt(l, cn)
        opt = emission.expected_read_count(l, cn)

        error = np.sum(unopt - opt)

        self.assertAlmostEqual(error, 0.0, places=3)


    def test_log_likelihood_cn_partial_phi_opt(self):

        cn, h, l, phi, r, x = self.generate_simple_data()

        emission = likelihood_unopt.NegBinLikelihood()
        emission.h = h
        emission.phi = phi
        emission.r = r

        unopt = emission._log_likelihood_partial_phi_unopt(x, l, cn)
        opt = emission._log_likelihood_partial_phi(x, l, cn)

        error = np.sum(unopt - opt)

        self.assertAlmostEqual(error, 0.0, places=3)


    def test_log_likelihood_cn_negbin_opt(self):

        mu, x = self.generate_count_data()

        dist = likelihood_unopt.NegBinDistribution()

        unopt = dist.log_likelihood_unopt(x, mu)
        opt = dist.log_likelihood(x, mu)

        error = np.sum(unopt - opt)

        self.assertAlmostEqual(error, 0.0, places=3)


    def test_log_likelihood_cn_poisson_opt(self):

        mu, x = self.generate_count_data()

        dist = likelihood_unopt.PoissonDistribution()

        unopt = dist.log_likelihood_unopt(x, mu)
        opt = dist.log_likelihood(x, mu)

        error = np.sum(unopt - opt)

        self.assertAlmostEqual(error, 0.0, places=3)


    def test_log_likelihood_cn_negbin_partial_h_opt(self):

        cn, h, l, phi, r, x = self.generate_simple_data()

        emission = likelihood_unopt.NegBinLikelihood()
        emission.h = h
        emission.phi = phi
        emission.r = r

        unopt = emission._log_likelihood_partial_h_unopt(x, l, cn)
        opt = emission._log_likelihood_partial_h(x, l, cn)

        error = np.sum(unopt - opt)

        self.assertAlmostEqual(error, 0.0, places=3)


    def test_log_likelihood_cn_negbin_partial_r_opt(self):

        mu, x = self.generate_count_data()

        dist = likelihood_unopt.NegBinDistribution()

        unopt = dist.log_likelihood_partial_r_unopt(x, mu)
        opt = dist.log_likelihood_partial_r(x, mu)

        error = np.sum(unopt - opt)

        self.assertAlmostEqual(error, 0.0, places=3)


    def test_log_likelihood_cn_poisson_partial_h_opt(self):

        cn, h, l, phi, r, x = self.generate_simple_data()

        emission = likelihood_unopt.PoissonLikelihood()
        emission.h = h
        emission.phi = phi

        unopt = emission._log_likelihood_partial_h_unopt(x, l, cn)
        opt = emission._log_likelihood_partial_h(x, l, cn)

        error = np.sum(unopt - opt)

        self.assertAlmostEqual(error, 0.0, places=3)


    def test_log_likelihood_cn_partial_phi(self):

        cn, h, l, phi, r, x = self.generate_simple_data()

        emission = likelihood.NegBinLikelihood()
        emission.h = h
        emission.phi = phi
        emission.r = r

        def evaluate_log_likelihood(phi, x, l, cn):
            emission.phi = phi
            return np.sum(emission.log_likelihood(x, l, cn))

        def evaluate_log_likelihood_partial_phi(phi, x, l, cn):
            emission.phi = phi
            return emission._log_likelihood_partial_phi(x, l, cn)[:,0]

        assert_grad_correct(evaluate_log_likelihood,
            evaluate_log_likelihood_partial_phi, phi,
            x, l, cn)


    def test_log_likelihood_cn_negbin_partial_h(self):

        cn, h, l, phi, r, x = self.generate_simple_data()

        def evaluate_log_likelihood(h, x, l, cn, phi):
            emission = likelihood.NegBinLikelihood()
            emission.h = h
            emission.phi = phi
            emission.r = r
            return emission.log_likelihood(x, l, cn)

        def evaluate_log_likelihood_partial_h(h, x, l, cn, phi):
            emission = likelihood.NegBinLikelihood()
            emission.h = h
            emission.phi = phi
            emission.r = r
            return emission._log_likelihood_partial_h(x, l, cn)

        assert_grad_correct(evaluate_log_likelihood,
            evaluate_log_likelihood_partial_h, h,
            x, l, cn, phi)


    def test_log_likelihood_cn_negbin_partial_r(self):

        mu, x = self.generate_count_data()

        dist = likelihood_unopt.NegBinDistribution()

        def evaluate_log_likelihood(r):
            dist.r = r
            return dist.log_likelihood(x, mu)

        def evaluate_log_likelihood_partial_r(r):
            dist.r = r
            return dist.log_likelihood_partial_r(x, mu)[:,None]

        r = np.array([75.])

        assert_grad_correct(evaluate_log_likelihood,
            evaluate_log_likelihood_partial_r, r)


    def test_log_likelihood_cn_poisson_partial_h(self):

        cn, h, l, phi, r, x = self.generate_simple_data()

        def evaluate_log_likelihood(h, x, l, cn, phi):
            emission = likelihood.PoissonLikelihood()
            emission.h = h
            emission.phi = phi
            return emission.log_likelihood(x, l, cn)

        def evaluate_log_likelihood_partial_h(h, x, l, cn, phi):
            emission = likelihood.PoissonLikelihood()
            emission.h = h
            emission.phi = phi
            return emission._log_likelihood_partial_h(x, l, cn)

        assert_grad_correct(evaluate_log_likelihood,
            evaluate_log_likelihood_partial_h, h,
            x, l, cn, phi)


    def test_learn_negbin_r_partial(self):

        N = 1000

        l = np.random.uniform(low=100000, high=1000000, size=N)
        x = np.random.uniform(low=0.02, high=0.1, size=N) * l

        negbin = remixt.likelihood.NegBinDistribution()

        g0 = remixt.paramlearn._sum_adjacent(x / l) / 2.
        r0 = 100.
        param0 = np.concatenate([g0, [r0]])

        assert_grad_correct(remixt.paramlearn.nll_negbin,
            remixt.paramlearn.nll_negbin_partial_param, param0,
            negbin, x, l)


    def test_log_likelihood_cn_betabin_partial_p(self):

        p, x = self.generate_allele_data()

        dist = likelihood.BetaBinDistribution()

        def evaluate_log_likelihood(p):
            return dist.log_likelihood(x, p).sum()

        def evaluate_log_likelihood_partial_p(p):
            return dist.log_likelihood_partial_p(x, p)

        assert_grad_correct(evaluate_log_likelihood,
            evaluate_log_likelihood_partial_p, p)


    def test_log_likelihood_cn_betabin_partial_M(self):

        p, x = self.generate_allele_data()

        dist = likelihood.BetaBinDistribution()

        def evaluate_log_likelihood(M):
            dist.M = M
            return dist.log_likelihood(x, p)

        def evaluate_log_likelihood_partial_M(M):
            dist.M = M
            return dist.log_likelihood_partial_M(x, p)[:,None]

        M = np.array([50.])

        assert_grad_correct(evaluate_log_likelihood,
            evaluate_log_likelihood_partial_M, M)


if __name__ == '__main__':
    unittest.main()

