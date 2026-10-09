# SYNTHETIC golden benchmark corpus — "Example Labor College" (FICTIONAL)

Every page here is invented for the APEX ONE golden benchmark. The institution, domains
(`*.invalid`, a TLD reserved by RFC 2606 so it can never resolve) and all numbers are fictional.
The corpus is *shaped like* a tuition-free work-college admissions situation (Berea-style) so that
the pipeline is exercised end-to-end, **without fabricating any real Berea College fact**.

Designed traps (the benchmark asserts each is handled):
* previous-cycle official page (2026 cycle) with a different deadline and TOEFL minimum -> STALE_CYCLE
* third-party blog with a wrong deadline, a wrong application fee and a wrong IELTS minimum -> official wins
* forum rumour that the SAT is required -> contradicted by official "test-optional"
* the official PDF independently confirms the critical values -> independent verification
* hedged language ("estimated") on the student contribution -> recorded on the claim
