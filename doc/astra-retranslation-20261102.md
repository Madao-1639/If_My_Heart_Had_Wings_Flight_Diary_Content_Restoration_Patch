# Chinese Corpus Retranslation Provenance

This note records the model and validation scope for the Chinese corpus update in this contribution.

## Baseline and scope

- Upstream baseline: v0.0.3, commit e85b9291fa003ac2478f1e6da9560fe268efc387.
- Scope: the existing 5,348 rows across the 25 JSONL files under resource/corpus/cn/.
- Each source row was retranslated from its Japanese text with AstraHigh. A centralized 184-row semantic and terminology revision was then applied with AstraHigh.
- LunaMax handled the engineering merge, JSONL preservation, source-diff verification, and focused pronoun/name audit.
- Existing non-cn fields, including historical src values, are preserved. This note records the actual translation source without rewriting that historical metadata.
- No generated payload, archive, or local game copy is included.

## Data and build verification

The native-corpus merge changed 5,020 cn values. The remaining 328 values match the upstream cn text exactly; they remain present in the complete row-key set and are not omissions from the merge. Row keys, row order, JSON field order, non-cn values, raw line structure, and baseline line endings were preserved.

The upstream builder reads the cn field directly into text slots. The integrated local candidate archive was validated at 1,168,066 bytes (SHA-256 54983b36e26a679290453d70fde1f502cf6bd394ee8890e6499e32afb7264c4a). Integration checks reported 5,348 target slots across 25 target members, 11,951 unchanged non-target slots, 26 unchanged non-target members, and unchanged member-name order.

## Focused name correction

A targeted audit traced the earlier unsupported “萤” insertions in AFT_003#348, #402, #405, #407, and #409 to “凜” in the old Gemini draft followed by the old normalization mapping “凜” to “萤”. The current translations for those rows remove the unsupported name. The audit also checked every current “萤/螢/蛍” occurrence and preserved genuine Hotaru references.

## Review status

The data merge and local structural/archive validation are complete. Human in-game review and feedback are still pending. This note does not claim full-corpus human semantic or visual validation.
