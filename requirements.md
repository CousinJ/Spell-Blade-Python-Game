# Sprint 2 Requirements

## Brief
Build a multi-component system in which different components communicate via messaging. Topic is open. Plausible directions:

- Real-time multiplayer game.
- Collaborative whiteboard or document editor.
- IoT dashboard with multiple sensor sources.
- Multi-agent simulation.
- Live event-driven feed (sports scores, stock ticks, social timelines).

This is the sprint where messaging-pattern vernacular is exercised under load.

## Mandatory Technical Requirements
- **≥3 distinct Enterprise Integration Patterns (EIPs)** implemented.
  - One **must** be **Publish-Subscribe** via **MQTT (`mqtt.uvucs.org`)** or **WebSockets**.
  - Other examples to choose from: Message Router, Content Filter, Content Enricher, Aggregator, Resequencer, Splitter, Message Translator.
- **≥1 explicit state chart** (XState or hand-rolled) governing a non-trivial workflow.
  - Document **states, events, transitions, and guards** in the README.
- **Persistence layer with audit trail / point-in-time history** (Perfect Framework: audit trails).
  - Every mutation must be reconstructable.
- **LLM-as-a-service component** is allowed but **not required**.
  - If used, must consume the class endpoint via the **Strategy pattern** from Sprint 1.

## Vernacular Requirements
Presentation must explicitly name and explain:

- **≥3 EIPs** (with citations to [enterpriseintegrationpatterns.com](https://www.enterpriseintegrationpatterns.com)).
- **≥2 GoF design patterns.**
- **The state-chart structure** (states / events / transitions / guards).
- **≥3 Perfect Framework concerns** addressed.

> LLM grader verifies pattern names match actual implementations.

## Demo Format
- **15-minute live demo + 5-minute Q&A.**
- Demo must include the system handling **at least one message-flow scenario in real time**.

## Deliverables
- Working system **deployed and reachable**.
- Source code with **`sprint-2-final`** tag.
- **README** documenting EIPs used, state chart, audit trail mechanism.
- Per-team-member **individual reflection** at `sprints/sprint-2-reflection.md`, due **24h after demo**.
