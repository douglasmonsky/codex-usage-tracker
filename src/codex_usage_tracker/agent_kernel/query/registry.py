"""Fail-closed reconciliation of the injected CK-08 contract mappings."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from .contracts import (
    MAX_PAGE_LIMIT,
    QueryContractError,
    QueryRequest,
)

_SELECTOR_ROLES = MappingProxyType(
    {
        "allowance_interval": "interval",
        "allowance_observation": "observation",
        "call": "call",
        "model_profile": "profile",
        "project": "project",
        "publication": "publication",
        "rate_card": "rate_card",
        "resource": "resource",
        "session": "session",
        "source_manifestation": "source",
        "state_change": "state",
        "tool": "tool",
        "turn": "turn",
    }
)


class QueryRegistryError(QueryContractError):
    """Injected query authorities do not reconcile into one safe registry."""


class QueryPlanNotAdmittedError(QueryRegistryError):
    """The plan is contract-visible but outside CK-08 admission."""


@dataclass(frozen=True, slots=True)
class PerformanceBudget:
    performance_class: str
    sql_p95_ms: int
    mcp_p95_ms: int
    query_calls: int
    evidence_calls: int
    response_bytes: int


@dataclass(frozen=True, slots=True)
class SourceBinding:
    relation: str
    fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AnswerBinding:
    field: str
    classification: str
    slot: str | None
    formula_id: str | None
    output_key: str | None


@dataclass(frozen=True, slots=True)
class FormulaUse:
    use_id: str
    formula_id: str
    source_relations: tuple[str, ...]
    required_parameters: tuple[str, ...]
    optional_parameters: tuple[str, ...]
    output_fields: tuple[str, ...]
    internal_use: bool


@dataclass(frozen=True, slots=True)
class QueryDefinition:
    """One reconciled, resolved question/plan entry."""

    question_id: str
    plan_id: str
    plan_version: int
    title: str
    stage: str
    support_classes: tuple[str, ...]
    intent_phrases: tuple[str, ...]
    request_schema: Mapping[str, Any]
    gates: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    required_measurements: tuple[str, ...]
    logical_primitives: tuple[str, ...]
    operations: tuple[str, ...]
    grades: Mapping[str, str]
    formula_ids: tuple[str, ...]
    coverage_requirements: tuple[str, ...]
    evidence_classes: tuple[str, ...]
    selector_kinds: tuple[str, ...]
    required_evidence: tuple[tuple[str, str], ...]
    order: tuple[str, ...]
    default_rows: int
    maximum_rows: int
    exact_count_default: bool
    performance_classes: tuple[str, ...]
    performance_budgets: tuple[PerformanceBudget, ...]
    permitted_sources: tuple[SourceBinding, ...]
    direct_bindings: tuple[AnswerBinding, ...]
    formula_bindings: tuple[AnswerBinding, ...]
    formula_uses: tuple[FormulaUse, ...]
    status: str = "resolved"

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_schema", MappingProxyType(dict(self.request_schema)))
        object.__setattr__(self, "grades", MappingProxyType(dict(self.grades)))

    @property
    def evidence_selector_kinds(self) -> tuple[str, ...]:
        return self.selector_kinds

    @property
    def admitted(self) -> bool:
        """CK-08 admits only Foundation and Cutover named plans."""

        return self.status == "resolved" and self.stage in {"Foundation", "Cutover"}

    @property
    def limits(self) -> tuple[int, int, bool]:
        return self.default_rows, self.maximum_rows, self.exact_count_default

    def validate_request(self, request: QueryRequest) -> None:
        if not isinstance(request, QueryRequest):
            raise QueryRegistryError("query registry accepts only QueryRequest values")
        if (
            request.question_id != self.question_id
            or request.plan_id != self.plan_id
            or request.plan_version != self.plan_version
        ):
            raise QueryRegistryError("request does not match the selected registry entry")

        required = self.request_schema["required"]
        optional = self.request_schema["optional"]
        supplied = set(request.parameters)
        missing = set(required) - supplied
        unknown = supplied - set(required) - set(optional)
        if missing or unknown:
            raise QueryRegistryError(
                f"request parameters mismatch; missing={sorted(missing)}, unknown={sorted(unknown)}"
            )
        for name, value in request.parameters.items():
            declaration = required.get(name, optional.get(name))
            expected = declaration.get("type") if isinstance(declaration, Mapping) else None
            if expected == "integer":
                valid = isinstance(value, int) and not isinstance(value, bool)
            elif expected == "object":
                valid = isinstance(value, Mapping)
            elif expected == "string":
                valid = isinstance(value, str)
            elif expected == "boolean":
                valid = isinstance(value, bool)
            elif expected == "number":
                valid = isinstance(value, (int, float)) and not isinstance(value, bool)
            else:
                raise QueryRegistryError(f"parameter {name!r} has an unsupported type declaration")
            if not valid:
                raise QueryRegistryError(f"parameter {name!r} must be {expected!r}")

        if set(request.gates) != set(self.gates) or any(
            request.gates.get(gate) is not True for gate in self.gates
        ):
            raise QueryRegistryError("request must supply all declared gates as true")
        supplied_evidence = tuple(
            (selection.role, selection.selector_kind)
            for selection in request.required_evidence
        )
        if supplied_evidence != self.required_evidence:
            raise QueryRegistryError(
                "required evidence role/kind sequence mismatch; "
                f"expected={self.required_evidence}, actual={supplied_evidence}"
            )
        if request.page.limit is not None and request.page.limit > self.maximum_rows:
            raise QueryRegistryError(
                f"page limit exceeds {self.plan_id} maximum of {self.maximum_rows}"
            )


RegistryEntry = QueryDefinition


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise QueryRegistryError(f"{label} must be a mapping")
    if any(not isinstance(key, str) for key in value):
        raise QueryRegistryError(f"{label} keys must be strings")
    return value


def _sequence(value: Any, label: str) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise QueryRegistryError(f"{label} must be an ordered sequence")
    return tuple(value)


def _string_sequence(value: Any, label: str) -> tuple[str, ...]:
    result = _sequence(value, label)
    if any(not isinstance(item, str) or not item.strip() for item in result):
        raise QueryRegistryError(f"{label} must contain non-empty strings")
    if len(set(result)) != len(result):
        raise QueryRegistryError(f"{label} must not contain duplicates")
    return result


def _records(contract: Mapping[str, Any], key: str, identity: str, label: str) -> tuple[Mapping[str, Any], ...]:
    raw = contract.get(key)
    if isinstance(raw, Mapping):
        records = []
        for record_id, record in raw.items():
            item = _mapping(record, f"{label}[{record_id!r}]")
            item = dict(item)
            item.setdefault(identity, record_id)
            records.append(item)
        return tuple(records)
    record_values = _sequence(raw, label)
    result = []
    for index, record in enumerate(record_values):
        result.append(_mapping(record, f"{label}[{index}]"))
    return tuple(result)


def _by_unique(records: Sequence[Mapping[str, Any]], key: str, label: str) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for index, record in enumerate(records):
        value = record.get(key)
        if not isinstance(value, str) or not value:
            raise QueryRegistryError(f"{label}[{index}] has no non-empty {key}")
        if value in result:
            raise QueryRegistryError(f"duplicate {key}: {value}")
        result[value] = record
    return result


def _same_names(actual: Any, expected: Sequence[str], label: str) -> None:
    if isinstance(actual, Mapping):
        values = _string_sequence(tuple(actual), label)
    else:
        values = _string_sequence(actual, label)
    if set(values) != set(expected):
        raise QueryRegistryError(
            f"{label} mismatch; expected={sorted(expected)}, actual={sorted(values)}"
        )


def _same_order(actual: Any, expected: Any, label: str) -> None:
    values = _string_sequence(actual, label)
    if tuple(values) != tuple(expected):
        raise QueryRegistryError(f"{label} order mismatch; expected={tuple(expected)}, actual={values}")


def _positive_budget(record: Mapping[str, Any], key: str, label: str) -> int:
    value = record.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise QueryRegistryError(f"{label}.{key} must be a positive integer")
    return value


def _required_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise QueryRegistryError(f"{label} must be a non-empty string")
    return value


def _required_evidence_sequence(
    selector_kinds: Sequence[str],
    required_parameters: Sequence[str],
) -> tuple[tuple[str, str], ...]:
    result: list[tuple[str, str]] = []
    required = set(required_parameters)
    for kind in selector_kinds:
        if kind == "window":
            if {"current_window", "previous_window"} <= required:
                result.extend(
                    (
                        ("current_window", "window"),
                        ("previous_window", "window"),
                    )
                )
            else:
                result.append(("window", "window"))
            continue
        role = _SELECTOR_ROLES.get(kind)
        if role is None:
            raise QueryRegistryError(f"selector kind has no required evidence role: {kind}")
        result.append((role, kind))
    return tuple(result)


def _answer_bindings(record: Mapping[str, Any], label: str) -> tuple[AnswerBinding, ...]:
    result = []
    for index, item in enumerate(_sequence(record.get("fields"), f"{label}.fields")):
        binding = _mapping(item, f"{label}.fields[{index}]")
        classification = binding.get("classification")
        if classification not in {"direct_fact", "formula_output"}:
            raise QueryRegistryError(f"{label}.fields[{index}] has an unsupported classification")
        field = binding.get("field")
        if not isinstance(field, str) or not field:
            raise QueryRegistryError(f"{label}.fields[{index}] has no field")
        formula_id = binding.get("formula_id")
        output_key = binding.get("output_key")
        if classification == "formula_output" and (
            not isinstance(formula_id, str) or not isinstance(output_key, str) or not output_key
        ):
            raise QueryRegistryError(f"formula output binding {field!r} is incomplete")
        if classification == "direct_fact" and (formula_id is not None or output_key is not None):
            raise QueryRegistryError(f"direct binding {field!r} names formula output metadata")
        result.append(
            AnswerBinding(
                field=field,
                classification=classification,
                slot=binding.get("slot"),
                formula_id=formula_id,
                output_key=output_key,
            )
        )
    return tuple(result)


def _formula_uses(record: Mapping[str, Any], label: str) -> tuple[FormulaUse, ...]:
    result = []
    for index, item in enumerate(_sequence(record.get("uses"), f"{label}.uses")):
        use = _mapping(item, f"{label}.uses[{index}]")
        formula_id = use.get("formula_id")
        if not isinstance(formula_id, str) or not formula_id:
            raise QueryRegistryError(f"{label}.uses[{index}] has no formula ID")
        result.append(
            FormulaUse(
                use_id=use.get("use_id", f"{label}:{index}"),
                formula_id=formula_id,
                source_relations=_string_sequence(
                    use.get("canonical_relations", use.get("source_relations")),
                    f"{label}.uses[{index}].source_relations",
                ),
                required_parameters=_string_sequence(
                    use.get("required_parameters", ()), f"{label}.uses[{index}].required_parameters"
                ),
                optional_parameters=_string_sequence(
                    use.get("optional_parameters", ()), f"{label}.uses[{index}].optional_parameters"
                ),
                output_fields=_string_sequence(
                    use.get("output_fields", ()), f"{label}.uses[{index}].output_fields"
                ),
                internal_use=bool(use.get("internal_use", False)),
            )
        )
    return tuple(result)


def _performance_budgets(catalog: Mapping[str, Any]) -> dict[str, PerformanceBudget]:
    records = _records(catalog, "performance_classes", "id", "performance_classes")
    result = {}
    for record in records:
        performance_id = record.get("id")
        if not isinstance(performance_id, str) or not performance_id:
            raise QueryRegistryError("performance class has no ID")
        if performance_id in result:
            raise QueryRegistryError(f"duplicate performance class: {performance_id}")
        result[performance_id] = PerformanceBudget(
            performance_class=performance_id,
            sql_p95_ms=_positive_budget(record, "sql_p95_ms", performance_id),
            mcp_p95_ms=_positive_budget(record, "mcp_p95_ms", performance_id),
            query_calls=_positive_budget(record, "query_calls", performance_id),
            evidence_calls=record.get("evidence_calls", 0),
            response_bytes=_positive_budget(record, "response_bytes", performance_id),
        )
        if (
            isinstance(result[performance_id].evidence_calls, bool)
            or not isinstance(result[performance_id].evidence_calls, int)
            or result[performance_id].evidence_calls < 0
        ):
            raise QueryRegistryError(f"{performance_id}.evidence_calls must be non-negative")
    return result


def _source_bindings(plan: Mapping[str, Any], label: str) -> tuple[SourceBinding, ...]:
    result = []
    seen: set[str] = set()
    for index, source in enumerate(_sequence(plan.get("permitted_sources"), f"{label}.permitted_sources")):
        item = _mapping(source, f"{label}.permitted_sources[{index}]")
        relation = item.get("relation")
        if not isinstance(relation, str) or not relation or relation in seen:
            raise QueryRegistryError(f"{label}.permitted_sources has an invalid relation")
        fields = _string_sequence(item.get("fields"), f"{label}.permitted_sources[{index}].fields")
        seen.add(relation)
        result.append(SourceBinding(relation, fields))
    if not result:
        raise QueryRegistryError(f"{label} has no permitted sources")
    return tuple(result)


def _reconcile_scope_sources(selector: Mapping[str, Any], questions: Mapping[str, Mapping[str, Any]]) -> None:
    expected = {
        "Q-ALW-02": {
            "plan_id": "allowance_interval_events",
            "variants": {"empty_interval", "same_time_boundary"},
            "scope_source": "allowance_observation_pair",
        },
        "Q-OPS-01": {
            "plan_id": "latest_publication_delta",
            "variants": {"no_change", "recanonicalized_owner"},
            "scope_source": "latest_accepted_publication_delta",
        },
    }
    records = _records(selector, "plan_scope_sources", "question_id", "plan_scope_sources")
    actual = _by_unique(records, "question_id", "plan_scope_sources")
    if set(actual) != set(expected):
        raise QueryRegistryError("the four owner-scoped no-window cases are not preserved")
    for question_id, rule in expected.items():
        item = actual[question_id]
        if item.get("plan_id") != rule["plan_id"] or item.get("scope_source") != rule["scope_source"]:
            raise QueryRegistryError(f"owner scope does not reconcile for {question_id}")
        variants = set(_string_sequence(item.get("variants"), f"{question_id}.variants"))
        if variants != rule["variants"]:
            raise QueryRegistryError(f"owner scope variants do not reconcile for {question_id}")
        if "window" in questions[question_id].get("parameters", {}).get("required", ()):
            raise QueryRegistryError(f"{question_id} fabricates a generic window")
        if "window" in questions[question_id].get("parameters", {}).get("optional", ()):
            raise QueryRegistryError(f"{question_id} fabricates an optional generic window")


class QueryRegistry:
    """An immutable registry assembled only from explicitly injected authorities."""

    def __init__(
        self,
        entries: Sequence[QueryDefinition],
        *,
        catalog_version: int,
        catalog_schema: str,
    ) -> None:
        if len(entries) != 40:
            raise QueryRegistryError("CK-08 requires exactly 40 reconciled question entries")
        self._entries = tuple(entries)
        self._by_question = MappingProxyType({entry.question_id: entry for entry in self._entries})
        self._by_plan = MappingProxyType({entry.plan_id: entry for entry in self._entries})
        self.catalog_version = catalog_version
        self.catalog_schema = catalog_schema

    @property
    def entries(self) -> tuple[QueryDefinition, ...]:
        return self._entries

    @property
    def question_ids(self) -> tuple[str, ...]:
        return tuple(entry.question_id for entry in self._entries)

    @property
    def plan_ids(self) -> tuple[str, ...]:
        return tuple(entry.plan_id for entry in self._entries)

    def get(self, question_id: str) -> QueryDefinition:
        try:
            return self._by_question[question_id]
        except KeyError as error:
            raise QueryRegistryError(f"unknown question ID: {question_id}") from error

    def by_plan(self, plan_id: str) -> QueryDefinition:
        try:
            return self._by_plan[plan_id]
        except KeyError as error:
            raise QueryRegistryError(f"unknown plan ID: {plan_id}") from error

    def validate(self, request: QueryRequest) -> QueryDefinition:
        entry = self.get(request.question_id)
        if not entry.admitted:
            raise QueryPlanNotAdmittedError(
                f"plan is registry-visible but not admitted by CK-08: {entry.plan_id}"
            )
        entry.validate_request(request)
        return entry

    resolve = validate


def build_registry(
    question_catalog: Mapping[str, Any],
    plan_operands: Mapping[str, Any],
    formulas: Mapping[str, Any],
    selector_provenance: Mapping[str, Any],
) -> QueryRegistry:
    """Reconcile four injected authority mappings into one fail-closed registry."""

    catalog = _mapping(question_catalog, "question catalog")
    plans_contract = _mapping(plan_operands, "plan operand contract")
    formula_contract = _mapping(formulas, "formula contract")
    selector_contract = _mapping(selector_provenance, "selector provenance contract")
    expected_schemas = {
        "question catalog": "codex-usage-tracker.question-catalog.v1",
        "plan operand contract": "codex-usage-tracker.plan-operand-contract.v1",
        "formula contract": "codex-usage-tracker.formula-contract.v1",
        "selector provenance contract": "codex-usage-tracker.selector-provenance.v1",
    }
    for label, value in (
        ("question catalog", catalog),
        ("plan operand contract", plans_contract),
        ("formula contract", formula_contract),
        ("selector provenance contract", selector_contract),
    ):
        if value.get("schema") != expected_schemas[label]:
            raise QueryRegistryError(f"unsupported {label} schema")
    versions = tuple(value.get("version") for value in (catalog, plans_contract, formula_contract, selector_contract))
    if any(isinstance(version, bool) or not isinstance(version, int) for version in versions) or set(versions) != {1}:
        raise QueryRegistryError("contract versions must all be exactly 1")

    questions = _by_unique(_records(catalog, "questions", "question_id", "questions"), "question_id", "questions")
    plans = _by_unique(_records(plans_contract, "plans", "question_id", "plans"), "question_id", "plans")
    if len(questions) != 40 or len(plans) != 40:
        raise QueryRegistryError("catalog and plan operands must each contain exactly 40 entries")
    plan_ids = [plan.get("plan_id") for plan in plans.values()]
    if any(not isinstance(plan_id, str) or not plan_id for plan_id in plan_ids) or len(set(plan_ids)) != 40:
        raise QueryRegistryError("plan IDs must be present and unique")
    formula_defs = _by_unique(_records(formula_contract, "formulas", "id", "formulas"), "id", "formulas")
    bindings = _by_unique(
        _records(formula_contract, "answer_field_bindings", "question_id", "answer_field_bindings"),
        "question_id",
        "answer_field_bindings",
    )
    uses = _records(formula_contract, "formula_uses", "question_id", "formula_uses")
    uses_by_question: dict[str, list[Mapping[str, Any]]] = {question_id: [] for question_id in questions}
    for formula_record in uses:
        question_id = formula_record.get("question_id")
        if question_id not in uses_by_question:
            raise QueryRegistryError(f"formula use names unknown question: {question_id}")
        uses_by_question[question_id].append(formula_record)

    selector_kinds = _string_sequence(selector_contract.get("selector_kinds"), "selector_kinds")
    ownership = _by_unique(
        _records(selector_contract, "ownership", "kind", "selector ownership"), "kind", "selector ownership"
    )
    if set(ownership) != set(selector_kinds):
        raise QueryRegistryError("selector ownership must cover exactly the catalog selector kinds")
    provenance_contracts = _by_unique(
        _records(selector_contract, "provenance_contracts", "kind", "provenance_contracts"),
        "kind",
        "provenance_contracts",
    )
    for selector_kind, owner in ownership.items():
        provenance_kind = owner.get("provenance_kind")
        if provenance_kind not in provenance_contracts:
            raise QueryRegistryError(
                f"selector {selector_kind} names unknown provenance kind: {provenance_kind}"
            )
    performance = _performance_budgets(catalog)
    evidence_classes = _by_unique(
        _records(catalog, "evidence_classes", "id", "evidence_classes"), "id", "evidence_classes"
    )
    _reconcile_scope_sources(selector_contract, questions)

    entries: list[QueryDefinition] = []
    for question_id, question in questions.items():
        plan = plans.get(question_id)
        if plan is None:
            raise QueryRegistryError(f"question has no plan operand entry: {question_id}")
        binding = bindings.get(question_id)
        if binding is None:
            raise QueryRegistryError(f"question has no formula/direct binding entry: {question_id}")
        plan_id = question.get("plan_id")
        if not isinstance(plan_id, str) or plan.get("plan_id") != plan_id:
            raise QueryRegistryError(f"question/plan ID mismatch for {question_id}")
        if question.get("version") != 1 or plan.get("status") != "resolved":
            raise QueryRegistryError(f"question is not resolved at version 1: {question_id}")
        if plan.get("blocked_reason") is not None:
            raise QueryRegistryError(f"resolved plan carries a blocked reason: {question_id}")
        parameters = _mapping(question.get("parameters"), f"{question_id}.parameters")
        required = _string_sequence(parameters.get("required"), f"{question_id}.parameters.required")
        optional = _string_sequence(parameters.get("optional", ()), f"{question_id}.parameters.optional")
        if set(required) & set(optional):
            raise QueryRegistryError(f"required and optional parameters overlap: {question_id}")
        request_schema = _mapping(plan.get("request_schema"), f"{question_id}.request_schema")
        _same_names(request_schema.get("required"), required, f"{question_id}.request_schema.required")
        _same_names(request_schema.get("optional"), optional, f"{question_id}.request_schema.optional")
        if request_schema.get("additional_parameters") is not False:
            raise QueryRegistryError(f"request schema must reject additional parameters: {question_id}")
        gates = _string_sequence(plan.get("gates"), f"{question_id}.gates")
        coverage = _string_sequence(question.get("coverage_requirements"), f"{question_id}.coverage_requirements")
        if set(gates) != set(coverage):
            raise QueryRegistryError(f"plan gates do not match coverage requirements: {question_id}")
        logical_plan = _mapping(question.get("logical_plan"), f"{question_id}.logical_plan")
        primitives = _string_sequence(logical_plan.get("primitives"), f"{question_id}.logical_plan.primitives")
        operations = _string_sequence(logical_plan.get("operations"), f"{question_id}.logical_plan.operations")
        if logical_plan.get("compiler_id") is not None:
            raise QueryRegistryError(f"raw physical compiler is not admitted in CK-08: {question_id}")
        if set(_string_sequence(plan.get("fact_order"), f"{question_id}.fact_order")) != {
            "event_at_us_is_null", "event_at_us", "source_rank", "source_order", "event_kind_order", "logical_id", "transition_rank"
        }:
            raise QueryRegistryError(f"fact order is not the canonical total order: {question_id}")
        _same_order(plan.get("result_order"), question.get("order"), f"{question_id}.result_order")
        answers = _mapping(question.get("answers"), f"{question_id}.answers")
        grades = _mapping(answers.get("fields"), f"{question_id}.answers.fields")
        formula_ids = _string_sequence(answers.get("formulas", ()), f"{question_id}.answers.formulas")
        if any(value not in {"exact", "deterministic", "configured_estimate", "model_inference", "unsupported"} for value in grades.values()):
            raise QueryRegistryError(f"unsupported answer grade: {question_id}")
        for formula_id in formula_ids:
            if formula_id not in formula_defs:
                raise QueryRegistryError(f"unknown formula {formula_id} for {question_id}")
        answer_bindings = _answer_bindings(binding, question_id)
        if {item.field for item in answer_bindings} != set(grades) or len(answer_bindings) != len(grades):
            raise QueryRegistryError(f"answer bindings do not cover grades exactly: {question_id}")
        formula_binding_ids = {
            item.formula_id for item in answer_bindings if item.classification == "formula_output"
        }
        internal_formula_ids = set(_string_sequence(binding.get("internal_formula_ids", ()), f"{question_id}.internal_formula_ids"))
        if formula_binding_ids | internal_formula_ids != set(formula_ids) or formula_binding_ids & internal_formula_ids:
            raise QueryRegistryError(f"formula bindings do not reconcile: {question_id}")
        direct_bindings = tuple(item for item in answer_bindings if item.classification == "direct_fact")
        formula_bindings = tuple(item for item in answer_bindings if item.classification == "formula_output")
        question_uses = _formula_uses({"uses": uses_by_question[question_id]}, question_id)
        if {item.formula_id for item in question_uses} != set(formula_ids):
            raise QueryRegistryError(f"formula uses do not cover the question formulas: {question_id}")
        for use in question_uses:
            if set(use.source_relations) != set(primitives) or set(use.required_parameters) != set(required) or set(use.optional_parameters) != set(optional):
                raise QueryRegistryError(f"formula use authority does not reconcile: {question_id}")
        if {item.field for item in formula_bindings} != {
            field for use in question_uses for field in use.output_fields
        }:
            raise QueryRegistryError(f"formula output fields do not reconcile: {question_id}")
        evidence = _mapping(question.get("evidence"), f"{question_id}.evidence")
        evidence_ids = _string_sequence(evidence.get("classes"), f"{question_id}.evidence.classes")
        question_selectors = _string_sequence(evidence.get("selector_kinds"), f"{question_id}.evidence.selector_kinds")
        for evidence_id in evidence_ids:
            rule = evidence_classes.get(evidence_id)
            if rule is None:
                raise QueryRegistryError(f"unknown evidence class {evidence_id}: {question_id}")
            allowed = set(_string_sequence(rule.get("selector_kinds"), f"{evidence_id}.selector_kinds"))
            if not set(question_selectors) & allowed:
                raise QueryRegistryError(f"evidence class does not admit question selectors: {question_id}")
        admitted_by_classes = set().union(
            *(
                set(_string_sequence(evidence_classes[evidence_id].get("selector_kinds"), f"{evidence_id}.selector_kinds"))
                for evidence_id in evidence_ids
            )
        )
        if not set(question_selectors) <= admitted_by_classes:
            raise QueryRegistryError(f"evidence selectors exceed their classes: {question_id}")
        if any(selector not in ownership or not ownership[selector].get("provenance_kind") for selector in question_selectors):
            raise QueryRegistryError(f"selector provenance is incomplete: {question_id}")
        limits = _mapping(question.get("limits"), f"{question_id}.limits")
        default_rows = _positive_budget(limits, "default_rows", question_id)
        maximum_rows = _positive_budget(limits, "maximum_rows", question_id)
        if default_rows > maximum_rows or maximum_rows > MAX_PAGE_LIMIT:
            raise QueryRegistryError(f"row limits are outside the bounded page contract: {question_id}")
        if not isinstance(limits.get("exact_count_default"), bool):
            raise QueryRegistryError(f"exact-count default must be boolean: {question_id}")
        performance_ids = _string_sequence(question.get("performance_classes"), f"{question_id}.performance_classes")
        if any(performance_id not in performance for performance_id in performance_ids):
            raise QueryRegistryError(f"unknown performance class: {question_id}")
        if any(len(performance_id) == 0 for performance_id in performance_ids):
            raise QueryRegistryError(f"empty performance class: {question_id}")
        entries.append(
            QueryDefinition(
                question_id=question_id,
                plan_id=plan_id,
                plan_version=1,
                title=_required_string(question.get("title"), f"{question_id}.title"),
                stage=_required_string(question.get("stage"), f"{question_id}.stage"),
                support_classes=_string_sequence(question.get("support_classes"), f"{question_id}.support_classes"),
                intent_phrases=_string_sequence(question.get("intent_phrases"), f"{question_id}.intent_phrases"),
                request_schema={"required": request_schema["required"], "optional": request_schema["optional"]},
                gates=gates,
                required_capabilities=_string_sequence(question.get("required_capabilities"), f"{question_id}.required_capabilities"),
                required_measurements=_string_sequence(question.get("required_measurements"), f"{question_id}.required_measurements"),
                logical_primitives=primitives,
                operations=operations,
                grades=grades,
                formula_ids=formula_ids,
                coverage_requirements=coverage,
                evidence_classes=evidence_ids,
                selector_kinds=question_selectors,
                required_evidence=_required_evidence_sequence(
                    question_selectors,
                    required,
                ),
                order=_string_sequence(question.get("order"), f"{question_id}.order"),
                default_rows=default_rows,
                maximum_rows=maximum_rows,
                exact_count_default=limits["exact_count_default"],
                performance_classes=performance_ids,
                performance_budgets=tuple(performance[performance_id] for performance_id in performance_ids),
                permitted_sources=_source_bindings(plan, question_id),
                direct_bindings=direct_bindings,
                formula_bindings=formula_bindings,
                formula_uses=question_uses,
            )
        )
    return QueryRegistry(
        sorted(entries, key=lambda entry: entry.question_id),
        catalog_version=catalog["version"],
        catalog_schema=catalog["schema"],
    )


from_mappings = build_registry


__all__ = [
    "AnswerBinding",
    "FormulaUse",
    "PerformanceBudget",
    "QueryDefinition",
    "QueryPlanNotAdmittedError",
    "QueryRegistry",
    "QueryRegistryError",
    "RegistryEntry",
    "SourceBinding",
    "build_registry",
    "from_mappings",
]
