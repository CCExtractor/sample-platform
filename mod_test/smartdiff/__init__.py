"""Semantic ("smart") diff for subtitle regression outputs.

Unlike a raw line diff, this package classifies *how* two outputs differ
(timing shift, text change, missing/extra cues) so a person or an agent gets an
actionable answer instead of a wall of changed lines. Pure/Flask-decoupled so it
is fully unit-testable.
"""
