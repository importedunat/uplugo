# SPDX-License-Identifier: GPL-3.0-only
"""Allowlisted diagnostic data; no names, serials, paths or input history."""
import platform
from app_info import VERSION


def snapshot(models, stream_status, charge_entries, dependencies, session):
    controllers=[]
    for number,state in enumerate(models,1):
        reading=state.reading or {}
        transport=stream_status.get(state.port,{})
        history=charge_entries.get(state.identity,{})
        samples=history.get('samples',[])
        samples=[sample for sample in samples if isinstance(sample,dict) and
                 type(sample.get('capacity')) is int and type(sample.get('at')) in (int,float)]
        controllers.append(dict(controller=number,connected=state.connected,
            requested=state.requested,effective=state.effective,confirmed=state.confirmed,
            fresh=state.fresh,transition=state.transition,has_error=bool(state.error),
            battery=reading.get('capacity'),battery_status=reading.get('status'),
            virtual_started=bool(transport.get('virtual_started')),
            packets=transport.get('packets'),outputs=transport.get('outputs'),rejected=transport.get('rejected'),
            observed_samples=len(samples),observed_change=(samples[-1]['capacity']-samples[0]['capacity']) if len(samples)>1 else None,
            observed_minutes=round((samples[-1]['at']-samples[0]['at'])/60,1) if len(samples)>1 else None))
    return dict(app='Uplugo',version=VERSION,system=platform.system(),kernel=platform.release(),
                architecture=platform.machine(),session=session if session in {'x11','wayland'} else 'unknown',
                dependencies=[{'name':item['name'],'ok':bool(item['ok']),'required':bool(item['required'])} for item in dependencies],
                controllers=controllers,
                note='Battery change is an observation, not current, voltage, battery health or a charge-time estimate.')
