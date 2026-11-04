"""Structured field extraction from a claim or candidate excerpt --
docs/claim-linking-improvement-plan.md §2. Regex/lexicon methods only in this pass
(no spaCy dependency added); every field this module cannot find a signal for is
`ABSENT`, never a guess. Reuses `proposition/annotations.py`'s existing cue detectors
for condition/exception/temporal/cross-reference/attribution rather than
reimplementing them.
"""

from __future__ import annotations

import re

from wittgenstein.core.enums import (
    AnnotationCueType,
    ComparisonFieldName,
    ExtractionStatus,
    SegmentType,
)
from wittgenstein.proposition.annotations import annotate_candidate
from wittgenstein.proposition.candidates import PropositionCandidate
from wittgenstein.review.normalization import (
    extract_comparator,
    extract_frequency_duration,
    extract_numeric_value,
)
from wittgenstein.schemas.claim_comparison import ExtractedField
from wittgenstein.schemas.proposition import SourceSegment

#: cue_type -> the ComparisonFieldName it evidences. MODALITY_HEDGE and NEGATION map
#: onto both MODALITY/POLARITY (handled specially below, not through this table) and
#: their own dedicated fields; ATTRIBUTION doubles as a jurisdiction/source-authority
#: signal, per docs/claim-linking-improvement-plan.md's field list.
_CUE_TO_FIELD = {
    AnnotationCueType.CONDITION: ComparisonFieldName.CONDITION,
    AnnotationCueType.EXCEPTION: ComparisonFieldName.EXCEPTION,
    AnnotationCueType.TEMPORAL: ComparisonFieldName.TEMPORAL,
    AnnotationCueType.CROSS_REFERENCE: ComparisonFieldName.CROSS_REFERENCE,
    AnnotationCueType.ATTRIBUTION: ComparisonFieldName.JURISDICTION,
}

_MODAL_RE = re.compile(
    r"\b(must not|must|should not|should|may not|may|might|could|can not|cannot|can|"
    r"shall not|shall|required|prohibited|recommended)\b",
    re.IGNORECASE,
)
#: Copula/do-support fallback when no modal auxiliary is present (e.g. "is exempt",
#: "does allow", "does not permit") -- without this, a claim/source pair using plain
#: "is"/"are"/"does"/"do" rather than a modal would never get an entity/predicate
#: extracted at all.
#: Includes a small lexicon of common regulatory-prose main verbs ("applies"/"requires"/
#: "covers", and their negated/base forms) alongside true copulas -- these are not
#: auxiliaries, but they serve the same role here (a verb anchor for entity/predicate
#: extraction) and are common enough in this domain to name explicitly rather than
#: leave entity/predicate extraction failing on every sentence that uses one.
_COPULA_RE = re.compile(
    r"\b(is not|is|are not|are|was not|was|were not|were|"
    r"does not|does|do not|do|did not|did|"
    r"applies|apply|requires|require|covers|cover)\b",
    re.IGNORECASE,
)
_PREDICATE_AFTER_VERB_RE = re.compile(r"\b(?:be\s+)?(\w+(?:ed|ing)?)\b")
_LEADING_ARTICLE_RE = re.compile(r"^(a|an|the)\s+", re.IGNORECASE)
_TRAILING_SCOPE_PHRASE_RE = re.compile(r"\s+(?:in|for|under|within|operating in)\s+.+$", re.IGNORECASE)
_NEGATION_WORDS_RE = re.compile(r"\b(not|never|none|cannot|no longer|without|no)\b", re.IGNORECASE)


def _find_verb_start(text: str) -> re.Match[str] | None:
    """The first modal auxiliary, or (if none) the first copula -- the anchor both
    entity ("subject = text before the verb") and predicate extraction key off of.
    A single shared anchor keeps the two fields structurally consistent with each
    other, rather than each guessing independently.
    """

    return _MODAL_RE.search(text) or _COPULA_RE.search(text)


_UNIT_RE = re.compile(
    r"\b(%|percent|business days?|days?|weeks?|months?|years?|units?|hours?|minutes?)\b", re.IGNORECASE
)
_VERSION_RE = re.compile(r"\b(?:v\d+(?:\.\d+)*|Program Year \d{4}|\d{4}\s+edition)\b", re.IGNORECASE)
#: The `all|any|every` quantifier branch deliberately excludes a purely-numeric
#: following word (`(?!\d)`) -- "every 6 months" is a frequency/duration phrase, not a
#: population/scope quantifier, and without this exclusion it would be misread as a
#: scope token every time a claim states a numeric recurrence.
_POPULATION_SCOPE_RE = re.compile(
    r"\b(Class\s+[IVX]+(?:\s+(?:and|or|,)\s+Class\s+[IVX]+)*|"
    r"Zone\s+[A-Z0-9]+|Region\s+[A-Z0-9]+|District\s+[A-Z0-9]+|Area\s+[A-Z0-9]+|"
    r"all\s+(?!\d)\w+|any\s+(?!\d)\w+|every\s+(?!\d)\w+)\b"
)


def _absent(field_name: ComparisonFieldName) -> ExtractedField:
    return ExtractedField(
        field_name=field_name, extraction_method="regex", extraction_status=ExtractionStatus.ABSENT
    )


def _from_match(
    field_name: ComparisonFieldName, match: re.Match[str], *, value: dict | None = None
) -> ExtractedField:
    return ExtractedField(
        field_name=field_name,
        value=value if value is not None else {"surface_form": match.group(0)},
        raw_surface_form=match.group(0),
        source_span=(match.start(), match.end()),
        extraction_method="regex",
        extraction_status=ExtractionStatus.EXTRACTED,
        confidence=0.7,
    )


def _extract_entity(text: str) -> ExtractedField:
    """Entity/subject = the text before the first modal/copula verb, with a leading
    article stripped and a trailing scope/location prepositional phrase ("in Zone A",
    "under Exemption C") also stripped -- a crude but standard "subject precedes the
    verb" heuristic, deliberately not a plural-noun-suffix pattern (which
    false-matched words like "Class" -- ending in 's' -- as if they were plural nouns,
    and failed on singular subjects like "widget"). The trailing phrase is not
    discarded -- POPULATION_SCOPE has its own extractor for exactly that text -- this
    only keeps ENTITY from over-broadly absorbing a scope qualifier that belongs to a
    different component (so "Class III widgets in Zone A" doesn't fail to match a
    source's plain "Class III widgets" purely because of an appended scope phrase).
    """

    verb_match = _find_verb_start(text)
    if verb_match is None or verb_match.start() == 0:
        return _absent(ComparisonFieldName.ENTITY)
    raw_subject = text[: verb_match.start()].strip()
    article_match = _LEADING_ARTICLE_RE.match(raw_subject)
    subject_with_scope = raw_subject[article_match.end() :] if article_match else raw_subject
    scope_match = _TRAILING_SCOPE_PHRASE_RE.search(subject_with_scope)
    subject = subject_with_scope[: scope_match.start()] if scope_match else subject_with_scope
    if not subject:
        return _absent(ComparisonFieldName.ENTITY)
    start = verb_match.start() - len(raw_subject) + (article_match.end() if article_match else 0)
    end = start + len(subject)
    return ExtractedField(
        field_name=ComparisonFieldName.ENTITY,
        value={"surface_form": subject},
        raw_surface_form=subject,
        source_span=(start, end),
        extraction_method="regex",
        extraction_status=ExtractionStatus.EXTRACTED,
        confidence=0.6,
    )


def _extract_predicate(text: str) -> ExtractedField:
    """Predicate = the base verb group (modal/copula stripped of any negation
    particle) plus the following word. Both negation and the modal/copula's strength
    are deliberately excluded from the comparable predicate surface form -- POLARITY
    and MODALITY (separate fields) carry those distinctions, so a claim/source pair
    differing only by "not" or by modal strength ("must" vs "may") registers as a
    polarity or modality mismatch there, not (also, redundantly) a predicate mismatch
    that would incorrectly block predicate alignment and prevent rules C/D
    (qualification_required/contradiction_candidate) from ever being reached. Predicate
    itself compares only the base verb (e.g. "inspected").
    """

    verb_match = _find_verb_start(text)
    if verb_match is None:
        return _absent(ComparisonFieldName.PREDICATE)
    remainder = text[verb_match.end() :]
    next_word_match = _PREDICATE_AFTER_VERB_RE.search(remainder)
    if not next_word_match:
        return _absent(ComparisonFieldName.PREDICATE)
    is_modal = bool(_MODAL_RE.fullmatch(verb_match.group(0)))
    verb_group = verb_match.group(0)
    comparable_phrase = next_word_match.group(0).strip()
    start = verb_match.start()
    end = verb_match.end() + next_word_match.end()
    return ExtractedField(
        field_name=ComparisonFieldName.PREDICATE,
        value={
            "surface_form": comparable_phrase,
            "verb": next_word_match.group(1).lower(),
            "modal": verb_group.lower() if is_modal else None,
            "copula": verb_group.lower() if not is_modal else None,
        },
        raw_surface_form=comparable_phrase,
        source_span=(start, end),
        extraction_method="regex",
        extraction_status=ExtractionStatus.EXTRACTED,
        confidence=0.6,
    )


def _extract_polarity(text: str) -> ExtractedField:
    match = _NEGATION_WORDS_RE.search(text)
    if not match:
        return ExtractedField(
            field_name=ComparisonFieldName.POLARITY,
            value={"polarity": "positive"},
            extraction_method="regex",
            extraction_status=ExtractionStatus.EXTRACTED,
            confidence=0.5,
        )
    return _from_match(ComparisonFieldName.POLARITY, match, value={"polarity": "negative", "cue": match.group(0)})


_MODALITY_STRENGTH = {
    "must": 3,
    "must not": 3,
    "shall": 3,
    "required": 3,
    "prohibited": 3,
    "should": 2,
    "should not": 2,
    "recommended": 2,
    "may": 1,
    "may not": 1,
    "might": 1,
    "could": 1,
    "can": 1,
    "cannot": 1,
    "can not": 1,
}


def _extract_modality(text: str) -> ExtractedField:
    match = _MODAL_RE.search(text)
    if not match:
        return _absent(ComparisonFieldName.MODALITY)
    normalized = match.group(0).lower()
    strength = _MODALITY_STRENGTH.get(normalized)
    return _from_match(
        ComparisonFieldName.MODALITY, match, value={"modal": normalized, "strength": strength, "scale": "1-3"}
    )


def _extract_frequency_duration(text: str) -> ExtractedField:
    temporal = extract_frequency_duration(text)
    if temporal is None:
        return _absent(ComparisonFieldName.FREQUENCY_DURATION)
    idx = text.lower().find(temporal.surface_form.lower())
    span = (idx, idx + len(temporal.surface_form)) if idx >= 0 else None
    return ExtractedField(
        field_name=ComparisonFieldName.FREQUENCY_DURATION,
        value={
            "value": temporal.value,
            "unit": temporal.unit,
            "kind": temporal.kind,
            "calendar": temporal.calendar,
            "normalization_status": temporal.normalization_status,
            "domain_term": temporal.domain_term,
        },
        raw_surface_form=temporal.surface_form,
        source_span=span,
        extraction_method="regex+review.normalization.extract_frequency_duration",
        extraction_status=ExtractionStatus.EXTRACTED,
        confidence=0.6 if temporal.normalization_status == "normalized" else 0.4,
    )


def _extract_numeric_value(text: str) -> ExtractedField:
    result = extract_numeric_value(text)
    if result is None:
        return _absent(ComparisonFieldName.NUMERIC_VALUE)
    value, surface_form = result
    idx = text.find(surface_form)
    span = (idx, idx + len(surface_form)) if idx >= 0 else None
    return ExtractedField(
        field_name=ComparisonFieldName.NUMERIC_VALUE,
        value={"value": value},
        raw_surface_form=surface_form,
        source_span=span,
        extraction_method="regex",
        extraction_status=ExtractionStatus.EXTRACTED,
        confidence=0.7,
    )


def _extract_comparator(text: str) -> ExtractedField:
    result = extract_comparator(text)
    if result is None:
        return _absent(ComparisonFieldName.COMPARATOR)
    code, surface_form = result
    idx = text.lower().find(surface_form.lower())
    span = (idx, idx + len(surface_form)) if idx >= 0 else None
    return ExtractedField(
        field_name=ComparisonFieldName.COMPARATOR,
        value={"comparator": code},
        raw_surface_form=surface_form,
        source_span=span,
        extraction_method="regex",
        extraction_status=ExtractionStatus.EXTRACTED,
        confidence=0.7,
    )


def _extract_unit(text: str) -> ExtractedField:
    match = _UNIT_RE.search(text)
    if not match:
        return _absent(ComparisonFieldName.UNIT)
    return _from_match(ComparisonFieldName.UNIT, match, value={"unit": match.group(0).lower()})


def _extract_version(text: str) -> ExtractedField:
    match = _VERSION_RE.search(text)
    if not match:
        return _absent(ComparisonFieldName.VERSION)
    return _from_match(ComparisonFieldName.VERSION, match, value={"version": match.group(0)})


def _extract_population_scope(text: str) -> ExtractedField:
    """A claim/passage can name more than one independent scope qualifier (e.g. a
    widget class *and* a zone) -- all matches are captured, not just the first, since
    treating population_scope as a single opaque string would lose a second qualifier
    entirely (see `review/field_comparison.py::_compare_population_scope`, which
    compares these as a set, not an exact string).
    """

    matches = list(_POPULATION_SCOPE_RE.finditer(text))
    if not matches:
        return _absent(ComparisonFieldName.POPULATION_SCOPE)
    scopes = [m.group(0) for m in matches]
    first = matches[0]
    return ExtractedField(
        field_name=ComparisonFieldName.POPULATION_SCOPE,
        value={"scopes": scopes},
        raw_surface_form=", ".join(scopes),
        source_span=(first.start(), first.end()),
        extraction_method="regex",
        extraction_status=ExtractionStatus.EXTRACTED,
        confidence=0.7,
    )


def _extract_quantification(numeric: ExtractedField, comparator: ExtractedField) -> ExtractedField:
    if numeric.extraction_status != ExtractionStatus.EXTRACTED:
        return _absent(ComparisonFieldName.QUANTIFICATION)
    value = dict(numeric.value or {})
    if comparator.extraction_status == ExtractionStatus.EXTRACTED and comparator.value:
        value["comparator"] = comparator.value.get("comparator")
    return ExtractedField(
        field_name=ComparisonFieldName.QUANTIFICATION,
        value=value,
        raw_surface_form=numeric.raw_surface_form,
        source_span=numeric.source_span,
        extraction_method="regex",
        extraction_status=ExtractionStatus.EXTRACTED,
        confidence=numeric.confidence,
    )


def _extract_object_value(text: str, entity: ExtractedField, predicate: ExtractedField) -> ExtractedField:
    """A light heuristic: the remainder of the sentence after the predicate phrase,
    if both entity and predicate were found -- otherwise ABSENT rather than a guess.
    """

    if predicate.extraction_status != ExtractionStatus.EXTRACTED or predicate.source_span is None:
        return _absent(ComparisonFieldName.OBJECT_VALUE)
    remainder = text[predicate.source_span[1] :].strip(" .,;")
    if not remainder:
        return _absent(ComparisonFieldName.OBJECT_VALUE)
    return ExtractedField(
        field_name=ComparisonFieldName.OBJECT_VALUE,
        value={"surface_form": remainder},
        raw_surface_form=remainder,
        source_span=(predicate.source_span[1], len(text)),
        extraction_method="regex",
        extraction_status=ExtractionStatus.EXTRACTED,
        confidence=0.3,
    )


def _cue_based_fields(text: str) -> dict[ComparisonFieldName, ExtractedField]:
    """Runs the existing Tier-2 annotation detectors (condition/exception/temporal/
    cross-reference/attribution) over `text` and maps each cue type onto its
    ComparisonFieldName -- reused, not reimplemented.
    """

    segment = SourceSegment(
        segment_id="field-extraction-tmp",
        source_document_id="field-extraction-tmp",
        corpus_id="field-extraction-tmp",
        segment_type=SegmentType.SENTENCE,
        location="field-extraction-tmp",
        text=text,
        char_start=0,
        char_end=len(text),
        parser_version="field-extraction-1",
    )
    candidate = PropositionCandidate(
        candidate_id="field-extraction-tmp-cand1",
        source_segment_id=segment.segment_id,
        text=text,
        char_start=0,
        char_end=len(text),
        split_method="whole_text",
    )
    annotations = annotate_candidate(candidate)

    results: dict[ComparisonFieldName, ExtractedField] = {}
    for cue_type, field_name in _CUE_TO_FIELD.items():
        matches = [a for a in annotations if a.cue_type == cue_type]
        if not matches:
            results[field_name] = _absent(field_name)
            continue
        first = matches[0]
        results[field_name] = ExtractedField(
            field_name=field_name,
            value={"surface_form": first.matched_text, "all_matches": [m.matched_text for m in matches]},
            raw_surface_form=first.matched_text,
            source_span=(first.char_start, first.char_end),
            extraction_method="annotation_reuse",
            extraction_status=ExtractionStatus.EXTRACTED,
            confidence=0.6,
        )
    return results


def extract_fields(text: str) -> dict[ComparisonFieldName, ExtractedField]:
    """Extracts all 17 ComparisonFieldName types from `text`. Always returns an entry
    for every field (ABSENT when no signal), never omits a key.
    """

    entity = _extract_entity(text)
    predicate = _extract_predicate(text)
    numeric = _extract_numeric_value(text)
    comparator = _extract_comparator(text)

    fields: dict[ComparisonFieldName, ExtractedField] = {
        ComparisonFieldName.ENTITY: entity,
        ComparisonFieldName.PREDICATE: predicate,
        ComparisonFieldName.OBJECT_VALUE: _extract_object_value(text, entity, predicate),
        ComparisonFieldName.POLARITY: _extract_polarity(text),
        ComparisonFieldName.MODALITY: _extract_modality(text),
        ComparisonFieldName.QUANTIFICATION: _extract_quantification(numeric, comparator),
        ComparisonFieldName.POPULATION_SCOPE: _extract_population_scope(text),
        ComparisonFieldName.FREQUENCY_DURATION: _extract_frequency_duration(text),
        ComparisonFieldName.NUMERIC_VALUE: numeric,
        ComparisonFieldName.COMPARATOR: comparator,
        ComparisonFieldName.UNIT: _extract_unit(text),
        ComparisonFieldName.VERSION: _extract_version(text),
    }
    fields.update(_cue_based_fields(text))
    return fields
