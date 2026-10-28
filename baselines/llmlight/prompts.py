"""Inference prompts from the LLMLight and CoLLMLight repositories."""

from __future__ import annotations

from typing import Dict, Sequence


CANONICAL_PHASES = ("ETWT", "NTST", "ELWL", "NLSL")
LOCATION = {"N": "North", "S": "South", "E": "East", "W": "West"}
PHASE_EXPLANATIONS = {
    "NTST": "- NTST: Northern and southern through lanes.",
    "NLSL": "- NLSL: Northern and southern left-turn lanes.",
    "NTNL": "- NTNL: Northern through and left-turn lanes.",
    "STSL": "- STSL: Southern through and left-turn lanes.",
    "ETWT": "- ETWT: Eastern and western through lanes.",
    "ELWL": "- ELWL: Eastern and western left-turn lanes.",
    "ETEL": "- ETEL: Eastern through and left-turn lanes.",
    "WTWL": "- WTWL: Western through and left-turn lanes.",
}


LLMLIGHT_SYSTEM_PROMPT = (
    "You are an expert in traffic management. You can use your knowledge of "
    "traffic commonsense to solve this traffic signal control tasks."
)


def llmlight_state2text(lanes: Dict[str, object]) -> str:
    """Exact ``LLMTSCS.utils.my_utils.state2text`` presentation."""
    state_txt = ""
    for phase in CANONICAL_PHASES:
        lane_1 = phase[:2]
        lane_2 = phase[2:]
        obs_1 = lanes[lane_1]
        obs_2 = lanes[lane_2]
        queue_len_1 = int(obs_1.queue)
        queue_len_2 = int(obs_2.queue)
        cells_1 = obs_1.llmlight_cells
        cells_2 = obs_2.llmlight_cells
        seg_1_lane_1 = cells_1[0]
        seg_2_lane_1 = cells_1[1]
        seg_3_lane_1 = cells_1[2] + cells_1[3]
        seg_1_lane_2 = cells_2[0]
        seg_2_lane_2 = cells_2[1]
        seg_3_lane_2 = cells_2[2] + cells_2[3]

        state_txt += (
            f"Signal: {phase}\n"
            f"Relieves: {PHASE_EXPLANATIONS[phase][8:-1]}\n"
            f"- Early queued: {queue_len_1} ({LOCATION[lane_1[0]]}), "
            f"{queue_len_2} ({LOCATION[lane_2[0]]}), "
            f"{queue_len_1 + queue_len_2} (Total)\n"
            f"- Segment 1: {seg_1_lane_1} ({LOCATION[lane_1[0]]}), "
            f"{seg_1_lane_2} ({LOCATION[lane_2[0]]}), "
            f"{seg_1_lane_1 + seg_1_lane_2} (Total)\n"
            f"- Segment 2: {seg_2_lane_1} ({LOCATION[lane_1[0]]}), "
            f"{seg_2_lane_2} ({LOCATION[lane_2[0]]}), "
            f"{seg_2_lane_1 + seg_2_lane_2} (Total)\n"
            f"- Segment 3: {seg_3_lane_1} ({LOCATION[lane_1[0]]}), "
            f"{seg_3_lane_2} ({LOCATION[lane_2[0]]}), "
            f"{seg_3_lane_1 + seg_3_lane_2} (Total)\n\n"
        )
    return state_txt


def llmlight_user_prompt(state_txt: str) -> str:
    """Exact user message returned by ``LLMTSCS.utils.my_utils.getPrompt``."""
    return (
        "A traffic light regulates a four-section intersection with northern, southern, eastern, and western "
        "sections, each containing two lanes: one for through traffic and one for left-turns. Each lane is "
        "further divided into three segments. Segment 1 is the closest to the intersection. Segment 2 is in the "
        "middle. Segment 3 is the farthest. In a lane, there may be early queued vehicles and approaching "
        "vehicles traveling in different segments. Early queued vehicles have arrived at the intersection and "
        "await passage permission. Approaching vehicles will arrive at the intersection in the future.\n\n"
        "The traffic light has 4 signal phases. Each signal relieves vehicles' flow in the group of two "
        "specific lanes. The state of the intersection is listed below. It describes:\n"
        "- The group of lanes relieving vehicles' flow under each signal phase.\n"
        "- The number of early queued vehicles of the allowed lanes of each signal.\n"
        "- The number of approaching vehicles in different segments of the allowed lanes of each signal.\n\n"
        + state_txt
        + "Please answer:\n"
        "Which is the most effective traffic signal that will most significantly improve the traffic "
        "condition during the next phase?\n\n"
        "Requirements:\n"
        "- Let's think step by step.\n"
        "- You can only choose one of the signals listed above.\n"
        "- You must follow the following steps to provide your analysis: Step 1: Provide your analysis "
        "for identifying the optimal traffic signal. Step 2: Answer your chosen signal.\n"
        "- Your choice can only be given after finishing the analysis.\n"
        "- Your choice must be identified by the tag: <signal>YOUR_CHOICE</signal>."
    )


def llmlight_alpaca_prompt(system_prompt: str, user_prompt: str) -> str:
    """Render the exact text format used to train and infer LLMLight.

    ``LLMTSCS`` does not apply a chat template to its fine-tuned LLMLight
    checkpoints.  It concatenates the two messages into this Alpaca-style
    completion prompt before tokenization/generation.
    """
    return (
        system_prompt
        + "\n\n### Instruction:\n"
        + user_prompt
        + "\n\n### Response:\n"
    )


COLLMLIGHT_SYSTEM_PROMPT = """You are a traffic signal control expert responsible for managing a four-way intersection within a larger road network. Your objective is to optimize both local and network-wide traffic flow and safety by selecting appropriate signal phases at each decision point. You must consider not only the traffic condition at your intersection, but also the influence on upstream and downstream intersections.

Your decision-making follows a two-stage process:

1. **Advance Traffic Reasoning (at timestep t-1):**  
   Based on current and historical traffic observations, you should conduct sufficient but necessary analysis to understand the key lanes, congestion risks, and propagation effects. Your goal is to provide a well-grounded recommendation and justification that can support the next-stage decision.

2. **Reactive Action (at timestep t):**  
   Given the real-time observation at timestep t and the prior reasoning, you must promptly determine the optimal signal phase. If significant changes are detected compared to previous reasoning, you should adapt your decision accordingly.

Follow all safety principles and ensure that each decision balances local urgency and global impact.

## Background Context
An intersection has 12 lanes: [NL, NT, NR, SL, ST, SR, EL, ET, ER, WL, WT, WR]. Each lane is labeled by direction and movement: N for north, S for south, E for east, W for west, L for left turn, T for through, and R for right turn. For instance, ET stands for the East Through lane, where traffic moves straight ahead from east to west. WL is the West Left-turn lane, where traffic turns left from west to south. Right turns are always allowed. There are four signal options: [ETWT, NTST, ELWL, NLSL]. For example, ETWT indicates the release of both the ET and WT lanes. The signal phase duration is set to thirty seconds.

## Note:
For each Lane X, when considering activating it, keep these in mind: 
    - NEVER NEVER let the occupancy of X's downstream lanes be close to 100% at any risk, as it will cause severe congestion, this is FIRST PRIORITY.
    - If the upstream or downstream information of X isn't mentioned, it means that they are in a good state with low occupancy.
    - You MUST consider how much the occupancy of X's downstream lanes will increase upon releasing lane X. 
    - You MUST delay the release of X if its downstream has a high occupancy rate.
    - If there are many high-occupancy lanes upstream of X and X's occupancy is not low, you MUST consider releasing X so as to help upstream lanes release.
    - You can't keep a lane waiting for too long. You MUST release the lane with excessive waiting time when the downstream condition allows.

"""


def collmlight_system_prompt(phase_duration: float) -> str:
    """Render the source prompt with the actual simulator control interval."""
    if float(phase_duration) == 30.0:
        return COLLMLIGHT_SYSTEM_PROMPT
    duration_text = (
        str(int(phase_duration))
        if float(phase_duration).is_integer()
        else str(phase_duration)
    )
    return COLLMLIGHT_SYSTEM_PROMPT.replace(
        "The signal phase duration is set to thirty seconds.",
        f"The signal phase duration is set to {duration_text} seconds.",
    )


ADVANCE_TRAFFIC_REASONING_TEMPLATE = """You are now in the **Advance Traffic Reasoning** phase (at time step {t0}).

Your goal is to perform deep but adaptive reasoning based on historical and current traffic conditions. This reasoning will guide the signal decision for the next time step {t1}.

---

{historical_observation}

---

{current_observation}


---

## Instruction
Please proceed through the following steps:
### Step 1: Identify Critical Lanes
Examine the current intersection and its upstream/downstream neighbors to identify critical local and neighboring lanes that are critical or congested and require attention; output as:
Local Critical Lanes: ...
Neighboring Critical Lanes: ...

### Step 2: Perform Adaptive Reasoning
Select and apply only the **necessary reasoning steps** to support an effective and fast decision at the next time step {t1}.

Suggested reasoning topics include (but are not limited to):  
- Local queue and waiting time analysis
- Upstream/downstream traffic influence
- Reflection on previous signal effectiveness
- Prediction of the traffic state at timestep {t1}
- Anticipated effects of activating specific signal phases (e.g., NTST, ETWT, NLSL, ELWL) at {t1}

### Step 3: Conditional Signal Suggestions
Provide one or more signal strategies that may be appropriate at time step {t1}.  
For each **suggested signal**, specify the situations under which it would be effective, including reasoning and expected effects.

Structure each strategy as:

- **Suggested Signal**: The signal phase that may be activated at time step {t1}  
    - **Applicable Conditions**: What kind of traffic pattern or development this signal is suitable for
    - **Rationale**: Why this signal is an appropriate choice under those conditions  
    - **Expected Effect**: The anticipated outcome if this signal is activated

### Step 4: Summary

## Notes
- Your reasoning should be adaptive: longer and deeper if traffic conditions are complex, shorter if simple.
- You may skip Steps 2 and 3 if the scenario is simple—for example, when there are no critical neighboring lanes.

## Output Format  
Your output should follow the structure below:

## Identify Critical Lanes

## Reasoning Topic 1

## Reasoning Topic 2

...

## Conditional Signal Suggestions

## Summary
"""


REACTIVE_ACTION_TEMPLATE = """You are now in the **Reactive Action** phase at time step {t1}.

Your goal is to quickly and accurately select the signal phase to activate at this moment, based on:
- The prior **Advance Traffic Reasoning (ATR)** conducted at time step {t0}
- The **Current Observation** at time step {t1}
- The **Local Signal Priority** ranking based on estimated waiting time reduction

---

# Advance Traffic Reasoning (ATR) at time step {t0}

{advance_traffic_reasoning_results}

---

{current_observation}

---

{local_signal_priority}

---

# Instruction

Please:

1. Compare the ATR suggestions with the current traffic state.  
2. If the current situation aligns with ATR predictions, select the recommended signal accordingly.  
3. If the current situation **deviates** from ATR, make necessary adjustments to respond to new patterns.  
4. If **upstream/downstream influence is minimal or negligible**, directly select the top-ranked signal from the Local Signal Priority table.  
5. Do not congest downstream lanes. When the occupancy of Lane X, plus that of any other X's downstream lanes, is close to 100%, you must delay the release of X.
6. Decide whether the ATR output was **actually useful** in your decision using the `used_atr` flag:  
   - `used_atr = 1`: The ATR output was referenced and influenced the decision.  
   - `used_atr = 0`: The decision was made independently of the ATR output.

---

# Output Format

Return your result in the following **structured JSON format**:

```json
{{
  "signal": "<Selected signal phase, e.g., ETWT, NTST, NLSL, ELWL>",
  "reason": "<Brief justification: why this signal is chosen based on traffic observation, local signal ranking, and (if applicable) the ATR suggestion.>",
  "used_atr": <0 or 1>
}}
```"""


def collmlight_atr_prompt(
    t0: int,
    t1: int,
    historical_observation: str,
    current_observation: str,
) -> str:
    return ADVANCE_TRAFFIC_REASONING_TEMPLATE.format(
        t0=t0,
        t1=t1,
        historical_observation=historical_observation,
        current_observation=current_observation,
    )


def collmlight_reactive_prompt(
    t0: int,
    t1: int,
    atr_result: str,
    current_observation: str,
    local_signal_priority: str,
) -> str:
    return REACTIVE_ACTION_TEMPLATE.format(
        t0=t0,
        t1=t1,
        advance_traffic_reasoning_results=atr_result,
        current_observation=current_observation,
        local_signal_priority=local_signal_priority,
    )


def local_signal_priority(ranking: Sequence[tuple[str, float]]) -> str:
    text = "# Local Signal Priority\n"
    text += "This rank only considers your own intersection and assumes the downstream allows the release.\n"
    text += "|Rank|Signal|Waiting Time Reduction|\n"
    for index, (phase, value) in enumerate(ranking, start=1):
        text += "|{}|{}|{:.1f} mins|\n".format(index, phase, value / 60)
    text += "\n"
    return text
