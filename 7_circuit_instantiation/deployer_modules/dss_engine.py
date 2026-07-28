# -*- coding: utf-8 -*-
"""
dss_engine.py
-------------
Backend-selecting factory for reaching the OpenDSS engine, duck-typed to the
COM object names used by power_flow_sim_daily_EV_STO_DG_deploy.py:

    DSSobj.AllowForms = False
    DSSobj.Start(0)
    DSStext    = DSSobj.Text
    DSStext.Command = "..."
    DSStext.Result
    DSScircuit = DSSobj.ActiveCircuit
    DSScircuit.Solution.Solve()
    DSScircuit.Solution.Converged

Windows keeps the real comtypes COM object (behaviour unchanged). Any other
platform gets a thin adapter over opendssdirect. Select with sys.platform,
override with the DSS_BACKEND=com|direct env var for cross-platform testing.

AllowForms/Command/Result/Converged are Python properties on the direct-mode
adapter, not methods, specifically so `DSScircuit.Solution.Converged` (no
parens) returns the real bool on both backends. opendssdirect exposes these
as callables; a missing pair of parens there silently returns a truthy bound
method instead of raising. Routing through a property makes that mistake
structurally impossible on the call sites that use this shim.
"""
import os
import sys


class _DirectText:
    """Adapts opendssdirect's Text.Command()/Text.Result() to COM's settable
    .Command / readable .Result property pair."""

    def __init__(self, dss_module):
        self._dss = dss_module
        self._result = ""

    @property
    def Command(self):
        return self._result

    @Command.setter
    def Command(self, cmd):
        self._dss.Text.Command(cmd)
        self._result = self._dss.Text.Result()

    @property
    def Result(self):
        return self._result


class _DirectSolution:
    """Adapts opendssdirect's Solution.* methods to COM's property-style access."""

    def __init__(self, dss_module):
        self._dss = dss_module

    def Solve(self):
        self._dss.Solution.Solve()

    @property
    def Converged(self):
        return bool(self._dss.Solution.Converged())

    @property
    def Mode(self):
        return self._dss.Solution.Mode()

    @property
    def Number(self):
        return self._dss.Solution.Number()

    @property
    def StepSize(self):
        return self._dss.Solution.StepSize()


class _DirectCircuit:
    def __init__(self, dss_module):
        self.Solution = _DirectSolution(dss_module)


class _DirectEngine:
    """opendssdirect-backed stand-in for the COM DSSobj (OpenDSSEngine.DSS)."""

    def __init__(self):
        import opendssdirect as dss_module
        self._dss = dss_module
        self.Text = _DirectText(dss_module)
        self.ActiveCircuit = _DirectCircuit(dss_module)

    @property
    def AllowForms(self):
        return self._dss.Basic.AllowForms()

    @AllowForms.setter
    def AllowForms(self, value):
        self._dss.Basic.AllowForms(value)

    def Start(self, x=0):
        return self._dss.Basic.Start(x)


def create_dss_engine(backend=None):
    """Factory: return an object duck-typed to the COM OpenDSSEngine.DSS root object.

    backend: "com" | "direct" | None (auto-detect: win32 -> com, else -> direct).
    Override via the DSS_BACKEND env var for cross-platform testing.
    """
    backend = backend or os.environ.get("DSS_BACKEND") or ("com" if sys.platform == "win32" else "direct")
    if backend == "com":
        import comtypes.client as cc
        return cc.CreateObject("OpenDSSEngine.DSS")
    if backend == "direct":
        return _DirectEngine()
    raise ValueError(f"Unknown DSS_BACKEND: {backend!r} (expected 'com' or 'direct')")
