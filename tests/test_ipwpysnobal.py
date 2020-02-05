#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
test_pysnobal
----------------------------------

Tests for `pysnobal` module.
"""

import os
import unittest

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from pysnobal.snobal_ipw import IPWPySnobal


class TestIPWPysnobal(unittest.TestCase):

    def setUp(self):
        pass

    def tearDown(self):
        os.remove('tests/test_data_point/snobal.pysnobal_c')

    def test_pysnobal_ipw_run(self):
        """ Test IPWPySnobal and compare with Snobal """

        # run PySnobal
        status = IPWPySnobal().run()
        self.assertTrue(status)

        # load in the outputs
        gold = pd.read_csv('tests/test_data_point/gold_ipw/gold.snobal.out',
                           header=None, index_col=0, sep=' ')
        new = pd.read_csv(
            'tests/test_data_point/snobal.pysnobal_c', header=None, index_col=0)

        self.assertTrue(new.shape == gold.shape)

        result = np.abs(gold - new)
        self.assertFalse(np.any(result > 0))
