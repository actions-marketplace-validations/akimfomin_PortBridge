# SPDX-License-Identifier: MIT
"""Structural checks for the scanner, in addition to compiled corpus controls."""

import unittest

from spirv_census import census


REGION = """\
%1 = OpTypeInt 32 0
%2 = OpConstant %1 0
%3 = OpConstant %1 1
%4 = OpConstant %1 2
%5 = OpConstant %1 3
%10 = OpLabel
OpSelectionMerge %40 None
OpSwitch %2 %20 1 %30
%20 = OpLabel
%21 = OpIAdd %1 %3 %5
%22 = OpIMul %1 %21 %4
%23 = OpBitwiseXor %1 %22 %5
%24 = OpShiftRightLogical %1 %23 %3
OpBranch %40
%30 = OpLabel
%31 = OpIAdd %1 %4 %5
%32 = OpIMul %1 %31 %4
%33 = OpBitwiseXor %1 %32 %5
%34 = OpShiftRightLogical %1 %33 %3
OpBranch %40
%40 = OpLabel
%41 = OpPhi %1 %24 %20 %34 %30
OpReturn
"""


class CensusTests(unittest.TestCase):
    def test_reports_a_profit_under_the_existing_planner_model(self):
        self.assertEqual(census(REGION), {
            "switches": 1, "direct_switches": 1,
            "plans": [{"header": "%10", "arms": 2, "body": 4,
                       "parameters": 1, "estimated_savings": 1}],
        })

    def test_rejects_external_uses_and_unsafe_shift_or_decorated_ops(self):
        edits = (
            REGION.replace("OpReturn", "%42 = OpPhi %1 %23 %20 %34 %30\nOpReturn"),
            REGION.replace("%3 = OpConstant %1 1", "%3 = OpConstant %1 32"),
            "OpDecorate %24 RelaxedPrecision\n" + REGION,
            REGION.replace("OpBranch %40\n%30", "OpBranch %30\n%30", 1),
        )
        for assembly in edits:
            with self.subTest(assembly=assembly):
                self.assertEqual(census(assembly)["plans"], [])


if __name__ == "__main__":
    unittest.main()
