<!-- gamma_manager (FREE) | role=critic lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=2.17s | action=critique-autopsy-exit-shape-dominated-hypothesis -->
<!-- reason: Sweep is grinding at -717 edge_capture (well below 771 floor, REJECT); the most actionable thing on the desk is the OPEN MED-priority autopsy hypothesis that has been left on the table for a full cycle. Three prior critic fires touched this file but never ran the actual stress-test -- last three outputs were file-opens and verbatim reviews, no adversarial objections. This is bounded, concrete, and produces a falsification answer the autopsy is missing. -->

{
  "analysis": {
    "error": "Agent failed (Function process_single_item_agent timed out after 90.0 seconds), API failed (API request returned None after all retries)]"
  }
}