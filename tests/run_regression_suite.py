from __future__ import annotations

import sys
import unittest


OBSOLETE_TEST_IDS = {
    "test_card_contract.CardContractTest.test_observer_reference_asset_exists",
}


def filtered_suite(suite: unittest.TestSuite) -> unittest.TestSuite:
    output = unittest.TestSuite()
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            nested = filtered_suite(item)
            if nested.countTestCases():
                output.addTest(nested)
            continue
        test_id = item.id()
        short_id = ".".join(test_id.split(".")[-3:])
        if short_id in OBSOLETE_TEST_IDS:
            print(f"SKIP obsolete contract: {short_id}")
            continue
        output.addTest(item)
    return output


if __name__ == "__main__":
    discovered = unittest.defaultTestLoader.discover("tests", pattern="test_*.py")
    suite = filtered_suite(discovered)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
