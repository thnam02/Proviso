862fd55467 excluded: Athena and Dune inherit from Trino, whose precision change was deliberate; following it is plausibly correct (not reverted upstream), so its child checks would penalise correct inheritance.
4ada15a429, a313c8bee1, d7fd83a7dc, 7f1cf60c88, ba0bff3d91, 9114355463 excluded: the child behaviour their checks
penalise already existed at the base commit for equivalent inputs (see research/ripple_mining/README.md, correction).
