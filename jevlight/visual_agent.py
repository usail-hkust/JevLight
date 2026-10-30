"""Bounded visual perception, neighbour routing, then a separate Jev decision."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import math
from pathlib import Path
import uuid

from .controller import phase_criteria
from .jev_client import JevResult
from .observation import CONTROLLED_LANES

VISUAL_PROMPT_VERSION = "vlalight-two-stage-v1"
COUNT_CRITERIA = {
    "none": "No visible vehicles for this movement.",
    "few": "One to three visible vehicles for this movement.",
    "several": "Four to eight visible vehicles for this movement.",
    "many": "Nine to fifteen visible vehicles for this movement.",
    "long": "Sixteen to thirty visible vehicles for this movement.",
    "very_long": "More than thirty visible vehicles for this movement.",
    "unknown": "The view does not distinguish this movement or its vehicle count.",
}
TREND_CRITERIA = {
    "growing": "More visible vehicles in the current view than the previous view.",
    "stable": "Approximately the same visible vehicle count in both views.",
    "shrinking": "Fewer visible vehicles in the current view than the previous view.",
    "unknown": "No previous view is supplied, or the change cannot be determined.",
}


class VisualAgent:
    """Estimate traffic from camera images and select a phase from those estimates."""

    image_agent = 'vlalight'
    prompt_version = VISUAL_PROMPT_VERSION

    def __init__(self, controller, *, cooperation=False):
        self.controller = controller
        self.cooperation = cooperation
        if cooperation:
            self.prompt_version += '-co-visual-v1'
        self.previous_views = {}
        self.unserved = {}
        self.last_step = None

    def _perception_request(self, observation, paths, step):
        assets = {}

        def references(files):
            refs = []
            for filename in files:
                ref = str(uuid.uuid4())
                assets[ref] = Path(filename)
                refs.append({"view": Path(filename).stem.rsplit("_", 1)[-1], "image": ref})
            return refs

        previous = self.previous_views.get(observation.intersection_id)
        state = {
            "current_views": references(paths),
            "previous_views": references(previous[1]) if previous else [],
        }
        mapping = (
            "Movement codes name the incoming side. EASTBOUND arrives from west (WT/WL); "
            "WESTBOUND from east (ET/EL); NORTHBOUND from south (ST/SL); "
            "SOUTHBOUND from north (NT/NL). T is through, L left turn. "
            "Use only visible vehicles in the relevant lanes, excluding right turns. "
            "If turn lanes cannot be distinguished, choose unknown rather than assigning "
            "all vehicles to both through and left turns. "
        )
        questions = {}
        for lane in CONTROLLED_LANES:
            for feature, instruction, criteria in (
                ("demand", "Estimate all visible vehicles in current_views, including queued vehicles.", COUNT_CRITERIA),
                ("queue", "Estimate the stopped/queued subset in current_views. It is part of demand, not additional vehicles.", COUNT_CRITERIA),
                ("trend", "Compare current_views to previous_views for this movement. Without a previous view choose unknown.", TREND_CRITERIA),
            ):
                questions[f"{lane}_{feature}"] = {
                    "type": "choice", "instructions": mapping + f"For {lane}: " + instruction,
                    "criteria": criteria,
                }
        return state, questions, assets

    def _perception_groups(self, request):
        return [request]

    def _parse_perception(self, result, questions):
        if result.error:
            raise ValueError(result.error)
        lanes = {}
        for key, question in questions.items():
            answer = result.answers.get(key)
            if not isinstance(answer, dict) or answer.get("type") != "choice":
                raise ValueError(f"missing visual estimate: {key}")
            choice = answer.get("choice")
            if choice not in question["criteria"]:
                raise ValueError(f"invalid visual estimate: {key}")
            confidence = answer.get("confidence")
            if confidence is not None:
                confidence = float(confidence)
                if not math.isfinite(confidence) or not 0 <= confidence <= 1:
                    raise ValueError(f"invalid visual confidence: {key}")
                if confidence < self.controller.min_confidence:
                    choice = "unknown"
            probabilities = answer.get("probabilities") or {}
            for value in probabilities.values():
                value = float(value)
                if not math.isfinite(value) or not 0 <= value <= 1:
                    raise ValueError(f"invalid visual probabilities: {key}")
            lane, feature = key.split("_", 1)
            lanes.setdefault(lane, {})[feature] = {"estimate": choice, "confidence": confidence}
        return lanes

    @staticmethod
    def _cooperative_view(observation, perceptions):
        """Route this step's image estimates using static lane connections only."""
        identities = sorted({
            ref['intersection_id']
            for lane in CONTROLLED_LANES
            for side in ('upstream', 'downstream')
            for ref in observation.lane_relations.get(lane, {}).get(side, [])
        })
        aliases = {identity: f'neighbour_{i + 1}' for i, identity in enumerate(identities)}
        links = {}
        for lane in CONTROLLED_LANES:
            links[lane] = {}
            for side in ('upstream', 'downstream'):
                links[lane][side] = []
                for ref in observation.lane_relations.get(lane, {}).get(side, []):
                    link = {'neighbour': aliases[ref['intersection_id']], 'movement': ref['lane']}
                    if link not in links[lane][side]:
                        links[lane][side].append(link)
        return {
            'neighbours': {aliases[identity]: {'visual_perception': perceptions.get(identity)}
                           for identity in identities},
            'possible_connections': links,
        }

    def _decision_request(self, observation, perceptions, prompt=None):
        state = {'visual_perception': perceptions[observation.intersection_id]}
        instructions = (
            "Choose a traffic signal using only visual_perception, which was estimated "
            "from the supplied camera images. Counts are visual ranges, not exact "
            "measurements. Queue is a subset of demand; do not add it twice. Unknown "
            "means unavailable visual evidence, never zero. Prefer phases serving "
            "larger visible demand and queues that are growing. Choose only from the "
            "provided phase criteria."
        )
        if self.cooperation:
            state['cooperative_view'] = self._cooperative_view(observation, perceptions)
            instructions += (
                " If cooperative_view is supplied, it contains only neighbouring camera "
                "estimates and static possible lane connections. Prioritize the local "
                "visible demand. Upstream demand is a possible future arrival, not a "
                "guaranteed arrival or a known turning route. Downstream queues can "
                "warn of spillback, but do not measure free storage. Never sum the same "
                "neighbour movement repeatedly across possible connections. Missing "
                "neighbours or movements are unknown, not zero. Do not infer their "
                "signal phases, exact counts, travel times or receiving capacity."
            )
        if prompt:
            instructions += "\nAdditional control instructions: " + prompt
        return state, {'phase_decision': {
            'type': 'choice', 'instructions': instructions, 'criteria': phase_criteria(observation)}}

    def decide(self, observations, images, step, prompt=None):
        controller = self.controller
        if controller.client.transport not in ("official", "local"):
            raise ValueError("vlalight visual agent requires an image-capable System One API")
        if controller.client.transport == "local" and not controller.client.model:
            raise ValueError("local VLALight runs require an explicit model id")
        if controller.packaging != "per_intersection" or controller.fallback != "previous":
            raise ValueError("vlalight visual agent requires per_intersection and previous fallback")
        if self.last_step is not None and step <= self.last_step:
            raise ValueError("visual steps must increase; use a new agent for a new run")
        normalized = {}
        for observation in observations:
            paths = images[observation.intersection_id]
            if isinstance(paths, (str, Path)) or len(paths) != 4:
                raise ValueError("vlalight visual agent requires four direction-labelled views")
            normalized[observation.intersection_id] = [Path(path) for path in paths]
        requests = [self._perception_request(o, normalized[o.intersection_id], step) for o in observations]
        groups = [self._perception_groups(request) for request in requests]
        jobs = [request for group in groups for request in group]
        with ThreadPoolExecutor(max_workers=controller.max_workers) as executor:
            batch_results = list(executor.map(lambda item: controller.client.evaluate(
                item[0], item[1], assets=item[2]), jobs))
        results, response_groups, offset = [], [], 0
        for group in groups:
            responses = batch_results[offset:offset + len(group)]
            offset += len(group)
            for response in responses:
                controller._record_result(response)
            response_groups.append(responses)
            if len(responses) == 1:
                results.append(responses[0])
            else:
                results.append(JevResult(
                    answers={key: response.answers[key] for request, response in zip(group, responses)
                             for key in request[1] if key in response.answers},
                    error='; '.join(response.error for response in responses if response.error) or None,
                    latency=sum(response.latency for response in responses),
                ))
        perceptions, errors = {}, {}
        for observation, request, result in zip(observations, requests, results):
            try:
                perceptions[observation.intersection_id] = self._parse_perception(result, request[1])
            except (AttributeError, TypeError, ValueError) as exc:
                errors[observation.intersection_id] = str(exc)
                if not result.error:
                    controller.total_failures += 1

        decisions = []
        for observation in observations:
            identity = observation.intersection_id
            if identity not in perceptions:
                continue
            state, questions = self._decision_request(observation, perceptions, prompt)
            decisions.append((observation, state, questions))
        # Every current perception is complete before any routed decision is sent.
        with ThreadPoolExecutor(max_workers=controller.max_workers) as executor:
            outcomes = list(executor.map(lambda item: controller.client.evaluate(item[1], item[2]), decisions))
        routed = {item[0].intersection_id: (item, result) for item, result in zip(decisions, outcomes)}
        actions, traces = {}, []
        for observation, request, perception_result, group, responses in zip(
                observations, requests, results, groups, response_groups):
            identity = observation.intersection_id
            phase_id = "phase_decision"
            if identity in routed:
                (_, state, questions), result = routed[identity]
                controller._record_result(result)
                signal, trace = controller._trace_decision(observation, step, phase_id,
                    result.answers.get(phase_id) if not result.error else None, result)
            else:
                state, questions = None, None
                result = JevResult(error=errors[identity])
                signal, trace = controller._trace_decision(observation, step, phase_id, None, result)
                trace["fallback"] = "visual_perception_failed"
            trace.update(input_mode="image", prompt_version=self.prompt_version,
                         visual_cooperation=self.cooperation,
                         image_agent=self.image_agent, mock=bool(controller.client.mock),
                         perception_state=request[0], perception_answers=perception_result.answers,
                         perception_error=errors.get(identity),
                         perception_latency_s=perception_result.latency,
                         image_paths=[str(path) for path in request[2].values()],
                         decision_state=state, decision_questions=questions,
                         response_model=result.model)
            if len(group) > 1:
                trace['perception_requests'] = [
                    {'state': item[0], 'questions': item[1],
                     'image_paths': {ref: str(path) for ref, path in item[2].items()},
                     **asdict(response)} for item, response in zip(group, responses)]
            actions[identity] = controller._phase_to_action(observation, signal)
            controller.previous_signals[identity] = signal
            traces.append(trace)
        self.previous_views = {identity: (step, paths) for identity, paths in normalized.items()}
        self.last_step = step
        return actions, traces


class JinanGroupedVisualAgent(VisualAgent):
    """Experimental Jinan-only lane masks and two opposite-approach requests."""

    image_agent = 'vlalight-grouped'
    prompt_version = 'vlalight-jinan-opposite-v2'

    def _perception_request(self, observation, paths, step):
        from .vlalight_images import isolate_jinan_movements
        state, questions, assets = super()._perception_request(observation, paths, step)
        return isolate_jinan_movements(state, questions, assets, paths[0].parent / 'movement_views_v2')

    def _perception_groups(self, request):
        state, questions, assets = request
        groups = []
        for movements in ({'NT', 'NL', 'ST', 'SL'}, {'ET', 'EL', 'WT', 'WL'}):
            subset = dict(state)
            for name in ('current_views', 'previous_views'):
                subset[name] = [view for view in state[name] if view['movement'] in movements]
            refs = {view['image'] for name in ('current_views', 'previous_views') for view in subset[name]}
            groups.append((subset,
                           {key: value for key, value in questions.items() if key.split('_')[0] in movements},
                           {ref: path for ref, path in assets.items() if ref in refs}))
        return groups
