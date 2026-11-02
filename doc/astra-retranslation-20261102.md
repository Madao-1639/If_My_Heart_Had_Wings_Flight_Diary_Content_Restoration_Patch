# Chinese Corpus Retranslation Provenance

This note records the model source, contribution scope, and validation limits for the proposed Chinese corpus update.

## Baseline and scope

- Upstream baseline: v0.0.3, commit e85b9291fa003ac2478f1e6da9560fe268efc387.
- Scope: all 5,348 existing rows across the 25 JSONL files under `resource/corpus/cn/`.
- Each Japanese source row was translated individually with GPT-6 Astra High. A centralized semantic and terminology revision covered 184 rows and was also produced with GPT-6 Astra High.
- GPT-6 Luna Max handled the engineering merge, JSONL preservation checks, source-diff verification, and focused pronoun/name audit.
- Existing non-`cn` fields, including historical `src` values, are preserved. This note records the translation source without rewriting that historical metadata.
- No generated payload, archive, or game binary is included.

## Data and build verification

The merge changed 5,020 `cn` values. The other 328 values match the upstream `cn` text exactly; they remain present in the complete row-key set and are not omissions. Row keys and order, JSON field order, every non-`cn` value, raw JSON line structure, and baseline LF line endings were preserved. Original Japanese text and text control codes remain intact.

The integrated local candidate archive was validated at 1,168,066 bytes (SHA-256 `54983b36e26a679290453d70fde1f502cf6bd394ee8890e6499e32afb7264c4a`). Integration checks reported 5,348 target slots across 25 target members, 11,951 unchanged non-target slots, 26 unchanged non-target members, and unchanged member-name order. The archive itself is not part of this contribution.

## Focused name correction

A targeted audit found that the earlier text at `AFT_003#348`, `#402`, `#405`, `#407`, and `#409` had mistaken a first-person reference for the character name 萤. The revised lines follow the Japanese referent and remove that unsupported name, while preserving genuine Hotaru references elsewhere.

## In-game review status

The candidate was launched from the official Steam installation for in-game checking. The user confirmed that text displayed correctly in the portion they tested and rated the translation quality positively. This feedback covers the tested portion only; it is not a claim that every route or the entire game received human review.
