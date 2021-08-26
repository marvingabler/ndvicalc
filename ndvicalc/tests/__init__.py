import unittest
import os
from . import test_main



def test():
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(test_main)
    return suite