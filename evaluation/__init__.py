"""Evaluation harness — scored, batch agent-scenario runs (inspired by agents_day2/validation).

Planned:
  tasks/        scenario task definitions (prompt + expected outcome)
  evaluator.py  scores an agent run against expected DB state / answer
  run_eval.py   batch runner + summary (accuracy, tool-call counts, cost)
"""
