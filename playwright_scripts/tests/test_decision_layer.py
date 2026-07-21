"""Behaviour tests for the queue decision layer.

Covers the four functions that decide whether a role reaches a human:
  _loc_ok            location policy
  _keep              fit + location policy (pre-tailor)
  _at_or_above_gate  the queue bar re-applied to an already-tailored card
  tailor_and_gate    correctness audit + the fit gate on the TAILORED result

Every expected value below is hand-computed from the documented policy, not read back
from the implementation. Run:
  cd playwright_scripts && ../.venv/bin/python -m unittest tests.test_decision_layer
"""

import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import build_local_queue as bq


class LocOkTests(unittest.TestCase):
    """NCR city names, the DL state code, and remote/WFH/hybrid match. Bare state codes
    and non-NCR Indian metros do not (documented at NCR_RE)."""

    def test_ncr_cities_match(self):
        for loc in ["Gurgaon, HR, IN", "Gurugram", "Noida, UP, IN", "Greater Noida",
                    "New Delhi, DL, IN", "Faridabad", "Ghaziabad", "Delhi NCR"]:
            with self.subTest(loc=loc):
                self.assertTrue(bq._loc_ok({"location": loc}))

    def test_remote_forms_match(self):
        for loc in ["Remote - India", "Work From Home", "WFH", "Hybrid, Pune"]:
            with self.subTest(loc=loc):
                self.assertTrue(bq._loc_ok({"location": loc}))

    def test_non_ncr_metros_do_not_match(self):
        for loc in ["Bangalore, KA, IN", "Mumbai, MH, IN", "Hyderabad", "Pune",
                    "Chennai, TN, IN", "Kolkata"]:
            with self.subTest(loc=loc):
                self.assertFalse(bq._loc_ok({"location": loc}))

    def test_bare_state_codes_are_too_broad_to_match(self):
        # Deliberate: "HR, IN" alone could be anywhere in Haryana, not just Gurgaon.
        for loc in ["HR, IN", "UP, IN"]:
            with self.subTest(loc=loc):
                self.assertFalse(bq._loc_ok({"location": loc}))

    def test_missing_or_empty_location(self):
        self.assertFalse(bq._loc_ok({"location": ""}))
        self.assertFalse(bq._loc_ok({"location": None}))
        self.assertFalse(bq._loc_ok({}))

    def test_substring_does_not_count_as_a_word(self):
        # "dl" is a word in the pattern, so it must not fire inside another word.
        self.assertFalse(bq._loc_ok({"location": "Kandla Port, GJ, IN"}))


class KeepTests(unittest.TestCase):
    """_keep(card, min_fit=0.60, standout=0.78, all_locations=False):
    keep if (fit >= 0.60 AND in NCR/remote) OR fit >= 0.78 anywhere."""

    MIN, STANDOUT = 0.60, 0.78

    def keep(self, fit, loc, all_locations=False):
        card = {"fit_score": fit, "location": loc}
        return bq._keep(card, self.MIN, self.STANDOUT, all_locations)

    def test_ncr_at_or_above_min_fit_is_kept(self):
        self.assertTrue(self.keep(0.65, "Gurgaon, HR, IN"))
        self.assertTrue(self.keep(0.60, "Noida, UP, IN"))  # boundary is inclusive

    def test_ncr_below_min_fit_is_dropped(self):
        self.assertFalse(self.keep(0.59, "Gurgaon, HR, IN"))
        self.assertFalse(self.keep(0.55, "New Delhi, DL, IN"))

    def test_non_ncr_needs_the_standout_score(self):
        self.assertFalse(self.keep(0.65, "Bangalore, KA, IN"))  # clears min, wrong city
        self.assertFalse(self.keep(0.77, "Bangalore, KA, IN"))  # just under standout
        self.assertTrue(self.keep(0.78, "Bangalore, KA, IN"))   # boundary is inclusive
        self.assertTrue(self.keep(0.91, "Mumbai, MH, IN"))

    def test_all_locations_drops_the_location_clause_only(self):
        self.assertTrue(self.keep(0.65, "Bangalore, KA, IN", all_locations=True))
        self.assertTrue(self.keep(0.60, "Chennai, TN, IN", all_locations=True))
        # The fit floor still applies.
        self.assertFalse(self.keep(0.59, "Gurgaon, HR, IN", all_locations=True))

    def test_missing_fit_score_is_treated_as_zero(self):
        self.assertFalse(bq._keep({"location": "Gurgaon"}, self.MIN, self.STANDOUT, False))
        self.assertFalse(bq._keep({"fit_score": None, "location": "Gurgaon"},
                                  self.MIN, self.STANDOUT, False))

    def test_string_fit_score_is_coerced(self):
        self.assertTrue(bq._keep({"fit_score": "0.82", "location": "Bangalore"},
                                 self.MIN, self.STANDOUT, False))


class AtOrAboveGateTests(unittest.TestCase):
    """The re-gate applied to carried-over cards. A card that already went through the
    tailor gauntlet is judged on its audited score alone: location and standout status were
    settled before it was tailored, so neither may resurrect a card below the bar."""

    def test_boundary_is_inclusive(self):
        self.assertTrue(bq._at_or_above_gate({"fit_score": 0.80}, 0.80))
        self.assertFalse(bq._at_or_above_gate({"fit_score": 0.79}, 0.80))

    def test_standout_score_does_not_readmit_a_card_below_the_gate(self):
        # The pre-tailor standout threshold (0.78) sits BELOW the tailored gate (0.80).
        # Routing this decision through _keep would let 0.78-0.799 cards from anywhere
        # survive a bar they never cleared, which is the exact staleness the re-gate exists
        # to prevent. Shown here as a contrast so the difference cannot silently regress.
        stale = {"fit_score": 0.79, "location": "Chennai"}
        self.assertTrue(bq._keep(stale, 0.80, 0.78, False), "_keep would readmit it")
        self.assertFalse(bq._at_or_above_gate(stale, 0.80), "the re-gate must not")

    def test_location_is_not_re_litigated(self):
        # Decided before tailoring. A non-NCR card that cleared the gate on merit stays.
        self.assertTrue(bq._at_or_above_gate({"fit_score": 0.84, "location": "Pune"}, 0.80))

    def test_missing_or_string_fit_score(self):
        self.assertFalse(bq._at_or_above_gate({}, 0.80))
        self.assertFalse(bq._at_or_above_gate({"fit_score": None}, 0.80))
        self.assertTrue(bq._at_or_above_gate({"fit_score": "0.91"}, 0.80))


class _Stub:
    """Records calls to tailor/verify so tests can assert how many passes ran."""

    def __init__(self, tailor_results, verify_results):
        self.tailor_results = list(tailor_results)
        self.verify_results = list(verify_results)
        self.tailor_calls = []
        self.verify_calls = []

    def tailor_run(self, role, focus=None, remove_claims=None):
        self.tailor_calls.append({"focus": focus, "remove_claims": remove_claims})
        return dict(self.tailor_results.pop(0))

    def verify_run(self, role, tailored_resume):
        self.verify_calls.append(tailored_resume)
        return dict(self.verify_results.pop(0))


def audit(clean=True, fit=0.9, fabrications=None, missing=None):
    return {
        "clean": clean,
        "fabrications": fabrications or [],
        "fit_score": fit,
        "missing_for_fit": missing or [],
        "reasoning_caveman": "",
    }


class TailorAndGateTests(unittest.TestCase):
    """The queue bar is the AUDITOR's fit_score for the tailored resume, gate 0.80.

    The role's raw pre-tailor score decides only whether tailoring is attempted, and must
    never be the number that reaches the card.
    """

    ROLE = {"id": "r1", "company": "Acme", "role": "BA", "fit_score": 0.61}

    def run_gate(self, stub, gate=bq.TAILORED_FIT_GATE, role=None):
        with patch.object(bq.tailor_mod, "run", stub.tailor_run), \
             patch.object(bq.verify_mod, "run", stub.verify_run), \
             patch.object(bq, "_read_tailored_resume", lambda rid: "resume body"):
            return bq.tailor_and_gate(dict(role or self.ROLE), gate)

    def test_clean_and_above_gate_is_kept_with_the_audited_score(self):
        stub = _Stub([{"id": "r1"}], [audit(fit=0.86)])
        tailored, verdict = self.run_gate(stub)
        self.assertIsNotNone(tailored)
        # 0.86 is the auditor's number. 0.61 is the role's raw pre-tailor score, which
        # must NOT be what lands on the card.
        self.assertEqual(tailored["fit_score"], 0.86)
        self.assertNotEqual(tailored["fit_score"], self.ROLE["fit_score"])
        self.assertIn("0.86", verdict)

    def test_gate_boundary_is_inclusive(self):
        stub = _Stub([{"id": "r1"}], [audit(fit=0.80)])
        tailored, _ = self.run_gate(stub)
        self.assertIsNotNone(tailored)
        self.assertEqual(tailored["fit_score"], 0.80)

    def test_just_below_gate_after_a_failed_retry_is_dropped(self):
        # First audit 0.72 (in the retry band), retry comes back no better -> drop.
        stub = _Stub([{"id": "r1"}, {"id": "r1"}],
                     [audit(fit=0.72, missing=["claims domain"]), audit(fit=0.70)])
        tailored, reason = self.run_gate(stub)
        self.assertIsNone(tailored)
        self.assertEqual(reason, "below_gate")
        self.assertEqual(len(stub.tailor_calls), 2, "should have spent exactly one retry")

    def test_retry_band_earns_exactly_one_honest_retry_that_can_rescue(self):
        stub = _Stub([{"id": "r1"}, {"id": "r1-retried"}],
                     [audit(fit=0.72, missing=["claims domain", "SQL"]), audit(fit=0.83)])
        tailored, verdict = self.run_gate(stub)
        self.assertIsNotNone(tailored)
        self.assertEqual(tailored["id"], "r1-retried")
        self.assertEqual(tailored["fit_score"], 0.83)
        # The retry must be steered by the auditor's missing_for_fit, not a blind redo.
        self.assertEqual(stub.tailor_calls[1]["focus"], ["claims domain", "SQL"])
        self.assertIn("0.83", verdict)

    def test_a_higher_scoring_but_unclean_retry_is_refused(self):
        # Correctness outranks fit: a 0.95 resume with a fabrication cannot be adopted.
        stub = _Stub([{"id": "r1"}, {"id": "r1-dirty"}],
                     [audit(fit=0.72), audit(clean=False, fit=0.95, fabrications=["fake cert"])])
        tailored, reason = self.run_gate(stub)
        self.assertIsNone(tailored)
        self.assertEqual(reason, "below_gate")

    def test_a_worse_scoring_retry_is_not_adopted(self):
        """A clean retry that scores WORSE than the first pass must be discarded.

        Both variants drop the role (a worse retry is below the gate by construction), so
        the return value cannot tell them apart. The difference is the operator-facing DROP
        diagnostic, which must quote the best honest attempt (0.79) and not the discarded
        retry (0.60). refresh_queue.sh surfaces this line, and an operator deciding whether
        a near-miss role is worth revisiting reads that number.
        """
        stub = _Stub([{"id": "r1"}, {"id": "r1-worse"}],
                     [audit(fit=0.79, missing=["SQL"]), audit(fit=0.60)])
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            tailored, reason = self.run_gate(stub)
        self.assertIsNone(tailored)
        self.assertEqual(reason, "below_gate")
        drop_line = next(l for l in err.getvalue().splitlines() if "DROP" in l)
        self.assertIn("0.79", drop_line)
        self.assertNotIn("0.60", drop_line)

    def test_below_retry_band_spends_no_retry(self):
        stub = _Stub([{"id": "r1"}], [audit(fit=0.40)])
        tailored, reason = self.run_gate(stub)
        self.assertIsNone(tailored)
        self.assertEqual(reason, "below_gate")
        self.assertEqual(len(stub.tailor_calls), 1, "0.40 is not worth a second model call")

    def test_retry_band_lower_boundary_is_inclusive(self):
        # RETRY_LOW is 0.55, so 0.55 retries and 0.54 does not.
        at_low = _Stub([{"id": "r1"}, {"id": "r1"}], [audit(fit=0.55), audit(fit=0.60)])
        self.run_gate(at_low)
        self.assertEqual(len(at_low.tailor_calls), 2)

        below_low = _Stub([{"id": "r1"}], [audit(fit=0.54)])
        self.run_gate(below_low)
        self.assertEqual(len(below_low.tailor_calls), 1)

    def test_fabrication_that_survives_two_strips_is_dropped(self):
        stub = _Stub([{"id": "r1"}] * 3,
                     [audit(clean=False, fit=0.95, fabrications=["fake cert"])] * 3)
        tailored, reason = self.run_gate(stub)
        self.assertIsNone(tailored)
        self.assertEqual(reason, "fabrication")
        # Original pass plus exactly two strip passes.
        self.assertEqual(len(stub.tailor_calls), 3)
        self.assertEqual(stub.tailor_calls[1]["remove_claims"], ["fake cert"])

    def test_fabrication_stripped_then_gated_on_fit(self):
        # A resume can be cleaned and still fail the fit bar. Both gates are independent.
        stub = _Stub([{"id": "r1"}, {"id": "r1"}, {"id": "r1"}],
                     [audit(clean=False, fit=0.9, fabrications=["fake cert"]),
                      audit(clean=True, fit=0.62),
                      audit(clean=True, fit=0.64)])
        tailored, reason = self.run_gate(stub)
        self.assertIsNone(tailored)
        self.assertEqual(reason, "below_gate")

    def test_gate_is_a_parameter_not_a_constant(self):
        stub = _Stub([{"id": "r1"}], [audit(fit=0.72)])
        tailored, _ = self.run_gate(stub, gate=0.70)
        self.assertIsNotNone(tailored)
        self.assertEqual(tailored["fit_score"], 0.72)

    def test_default_gate_is_the_documented_080(self):
        self.assertEqual(bq.TAILORED_FIT_GATE, 0.80)
        self.assertEqual(bq.RETRY_LOW, 0.55)

    def test_tailor_error_is_reported_not_swallowed_into_a_card(self):
        def boom(role, focus=None, remove_claims=None):
            raise RuntimeError("model down")
        with patch.object(bq.tailor_mod, "run", boom):
            tailored, reason = bq.tailor_and_gate(dict(self.ROLE))
        self.assertIsNone(tailored)
        self.assertEqual(reason, "tailor_error")

    def test_verify_error_drops_the_role_rather_than_trusting_the_author(self):
        def boom(role, tailored_resume):
            raise RuntimeError("auditor down")
        with patch.object(bq.tailor_mod, "run", lambda role, focus=None, remove_claims=None: {"id": "r1"}), \
             patch.object(bq.verify_mod, "run", boom), \
             patch.object(bq, "_read_tailored_resume", lambda rid: "resume body"):
            tailored, reason = bq.tailor_and_gate(dict(self.ROLE))
        self.assertIsNone(tailored)
        self.assertEqual(reason, "verify_error")


if __name__ == "__main__":
    unittest.main()
