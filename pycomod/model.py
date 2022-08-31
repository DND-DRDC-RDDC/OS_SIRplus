import pandas as pd
from pycomod.elements import *


# Class for building and running the model
class model:
    def __init__(self, init=None):

        # Time info
        self._t = sim_time()
        self._date = sim_date()

        # Run info
        self._dt = run_info(1)
        self._end = run_info(365)
        self._reps = run_info(100)

        # Model elements
        self._parameters = []
        self._samples = []
        self._equations = []
        self._init_flows = []
        self._priority_flows = []
        self._flows = []
        self._pools = []

        # Sub-models
        self._models = []

        # Output
        self._out = None  # Elements to track for output
        self._output = None  # Output from run
        self._output_mc = None  # Output from mc runs

        # Priority flow flag
        self._has_priority = False

        # Setup
        self._build()
        self._register()
        self._check_priority()
        if init is not None:
            self._init_cond(init)

    def _set_output(self, *args):
        self._out = list(args)

    def _build(self):
        # Implemented by sub-class
        pass

    def _register(self):
        # Get all attributes that are an instance of biulding_block and
        # organize them into lists

        elements = [x for x in self.__dict__.values()
                    if isinstance(x, (building_block, model))]

        for e in elements:
            if isinstance(e, sample):
                self._samples.append(e)
            elif isinstance(e, parameter):
                self._parameters.append(e)
            elif isinstance(e, equation):
                self._equations.append(e)
            elif isinstance(e, flow):
                if e.init:
                    self._init_flows.append(e)
                elif e.priority:
                    self._priority_flows.append(e)
                else:
                    self._flows.append(e)
            elif isinstance(e, pool):
                self._pools.append(e)
            elif isinstance(e, model):
                self._models.append(e)

    # Check self and sub-models for priority flows and updates _has_priority
    # flag
    def _check_priority(self):
        pri = False
        if len(self._priority_flows) > 0:
            pri = True

        for m in self._models:
            if m._has_priority:
                pri = True

        self._has_priority = pri

    def _init_cond(self, init):
        # Recursively apply initial conditions
        for key, value in init.items():
            if key == '_out':
                # Store elements of this model to be tracked for output
                self._out = value
            elif key in ['_dt', '_t', '_end', '_date', '_reps']:
                # If time and run info, push init to submodels
                self._push_init(key, value)
            else:
                # Set initial condition
                e = getattr(self, key)

                # If it's a model
                if isinstance(e, model):
                    e._init_cond(value)

                # If it's an element
                else:
                    e.init_cond(value)

    # Get the initial condition dict for this model
    def _get_init_dict(self):

        self._reset()

        d = {}
        elements = [(k, v) for k, v in self.__dict__.items()
                    if isinstance(v, (pool, parameter, model))]

        for k, v in elements:
            if isinstance(v, model):
                d[k] = v._get_init_dict()
            else:
                d[k] = v()

        return d

    # Get dataframes representing initial conditions for the model
    def _get_init_df(self, d=None, key=None):

        self._reset()

        if d is None:
            d = {}

        if key is None:
            key = 'init'

        # Create dict
        d[key] = {}

        # Add all elements to the dict
        elements = [(k, v) for k, v in self.__dict__.items()
                    if isinstance(v, (pool, parameter, model))]
        for k, v in elements:
            if isinstance(v, model):
                next_key = key + '.' + k
                d[key][k] = [next_key]
                v._get_init_df(d, next_key)
            else:
                if type(v()) == np.ndarray:
                    d[key][k] = v()
                else:
                    d[key][k] = [v()]

        # Add output tracking
        if self._out is None:
            d[key]['_out'] = [None]
        else:
            d[key]['_out'] = self._out

        # Add special settings to top level init
        if key == 'init':
            d[key]['_t'] = [self._t()]
            d[key]['_date'] = [self._date()]
            d[key]['_dt'] = [self._dt()]
            d[key]['_end'] = [self._end()]
            d[key]['_reps'] = [self._reps()]

        # Get max num rows
        rows = max([len(x) for x in d[key].values()])

        # Normalize column lengths
        for k in d[key].keys():
            add = rows - len(d[key][k])
            if add>0:
                d[key][k] = np.append(d[key][k], [None]*add)

        # Convert to dataframe
        d[key] = pd.DataFrame.from_dict(d[key])

        return d

    # Write an excel file containing initial conditions for the model
    def _write_excel_init(self, filename=None):
        d = self._get_init_df()

        if filename is None:
            filename = 'init.xlsx'

        with pd.ExcelWriter(filename) as writer:
            for k, v in d.items():
                v.to_excel(writer, sheet_name=k, index=False)

    # Set initial condition and push to submodels
    def _push_init(self, key, value):
        getattr(self, key).init_cond(value)
        for m in self._models:
            m._push_init(key, value)

    # UPDATE FUNCTIONS
    def _add_init_flows(self):

        # Recurse through sub-models
        for m in self._models:
            m._add_init_flows()

        # Add priority flows to pools
        for e in self._init_flows:
            e.add_flows()

    def _add_priority_flows(self):

        # Recurse through sub-models
        for m in self._models:
            m._add_priority_flows()

        # Add priority flows to pools
        for e in self._priority_flows:
            e.add_flows()

    def _add_flows(self):

        # Recurse through sub-models
        for m in self._models:
            m._add_flows()

        # Add flows to pools
        for e in self._flows:
            e.add_flows()

    def _update_pools(self, passno=1):

        # Recurse through sub-models
        for m in self._models:
            m._update_pools(passno)

        # Update pools (in order)
        for e in self._pools:
            e.update()
            e.save_hist(passno)

    def _update_equations(self, passno=1):

        # Recurse through sub-models
        for m in self._models:
            m._update_equations(passno)

        # Update equations (in order)
        for e in self._equations:
            e.update(self._t(), self._dt())
            e.save_hist(passno)

    def _update_init_flows(self, passno=1):

        # Recurse through sub-models
        for m in self._models:
            m._update_init_flows(passno)

        # Update init flows (order independent)
        for e in self._init_flows:
            e.update(self._dt())
        for e in self._init_flows:
            e.save_hist(passno)

    def _update_priority_flows(self, passno=1):

        # Recurse through sub-models
        for m in self._models:
            m._update_priority_flows(passno)

        # Update priority flows (order independent)
        for e in self._priority_flows:
            e.update(self._dt())
        for e in self._priority_flows:
            e.save_hist(passno)

    def _update_flows(self, passno=1):

        # Recurse through sub-models
        for m in self._models:
            m._update_flows(passno)

        # Update priority flows (order independent)
        for e in self._flows:
            e.update(self._dt())
        for e in self._flows:
            e.save_hist(passno)

    def _update_time(self, passno=1):

        # Recurse through sub-models
        for m in self._models:
            m._update_time(passno)

        # Update time info
        self._t.update(self._dt())
        self._t.save_hist(passno)

        self._date.update(self._dt())
        self._date.save_hist(passno)

    # Regular update sequence
    def _update_regular(self):

        self._add_flows()
        self._update_pools()
        self._update_equations()
        self._update_flows()

        self._update_init_flows()

    # Update sequence when priority flows are being used (2 passes)
    def _update_priority(self):

        # FIRST PASS FOR PRIORITY FLOWS
        self._add_priority_flows()
        self._update_pools()
        self._update_equations()
        self._update_flows()

        # SECOND PASS FOR REGULAR FLOWS
        self._add_flows()
        self._update_pools(2)
        self._update_equations(2)
        self._update_priority_flows()

        self._update_init_flows()

    # Update pass for all model elements
    def _update(self):

        # Update time
        self._update_time()

        # Update model elements
        if self._has_priority:
            self._update_priority()
        else:
            self._update_regular()

    def _reset_pools(self):

        # Recurse through sub-models
        for m in self._models:
            m._reset_pools()

        # Reset pools
        for e in self._pools:
            e.reset()

    def _reset_parameters(self):

        # Recurse through sub-models
        for m in self._models:
            m._reset_parameters()

        # Reset parameters
        for e in self._parameters:
            e.reset()

    def _reset_samples(self):

        # Recurse through sub-models
        for m in self._models:
            m._reset_samples()

        # Reset samples
        for e in self._samples:
            e.reset()

    def _reset_equations(self):

        # Recurse through sub-models
        for m in self._models:
            m._reset_equations()

        # Reset samples
        for e in self._equations:
            e.reset()

    def _reset_init_flows(self):

        # Recurse through sub-models
        for m in self._models:
            m._reset_init_flows()

        # Reset samples
        for e in self._init_flows:
            e.reset()

    def _reset_priority_flows(self):

        # Recurse through sub-models
        for m in self._models:
            m._reset_priority_flows()

        # Reset samples
        for e in self._priority_flows:
            e.reset()

    def _reset_flows(self):

        # Recurse through sub-models
        for m in self._models:
            m._reset_flows()

        # Reset samples
        for e in self._flows:
            e.reset()

    def _reset_time(self):

        # Recurse through sub-models
        for m in self._models:
            m._reset_time()

        self._t.reset()
        self._date.reset()

    def _reset_output(self):
        self._output = None

    def _reset_output_mc(self):
        self._output_mc = None

    # Reset all model elements to initial conditions
    def _reset(self):

        # Reset time
        self._reset_time()
        self._reset_output()

        # Reset all elements
        self._reset_pools()
        self._reset_parameters()
        self._reset_samples()
        self._reset_equations()
        self._reset_init_flows()
        self._reset_priority_flows()
        self._reset_flows()

        # Apply init flows
        self._add_init_flows()
        self._update_pools(2)
        self._update_equations(2)
        self._update_priority_flows(2)
        self._update_flows(2)

    # Save all output
    def _save_output(self):
        self._output = {}
        for key in self._out:
            e = getattr(self, key)

            if isinstance(e, building_block):
                self._output[key] = getattr(self, key).get_hist()
            elif isinstance(e, model):
                self._output[key] = e._save_output()

        return self._output

    # Do a run
    def _run(self, end=None, dt=None, start_time=None,
             start_date=None, init=None):

        # First apply initial conditions from init dict
        if init is not None:
            self._init_cond(init)

        # Override for any of the following run parameters
        if end is not None:
            self._push_init('_end', end)

        if dt is not None:
            self._push_init('_dt', dt)

        if start_time is not None:
            self._push_init('_t', start_time)

        if start_date is not None:
            self_push_init('_date', start_date)

        # Number of sim steps
        n = int(self._end()/self._dt())

        # Reset after applying initial conditions
        self._reset()

        # For each time step update everything
        for i in range(n):

            # Update model elements
            self._update()

        # Save output
        self._save_output()

    # Create container for mc output based on output from first replication
    def _init_output_mc(self, output):
        output_mc = {}
        for k, v in output.items():
            if not isinstance(v, dict):
                output_mc[k] = np.array([v])
            else:
                output_mc[k] = self._init_output_mc(v)

        return output_mc

    # Append output from subsequent replications to the mc output
    def _append_output_mc(self, output_mc, output):
        for k, v in output.items():
            if not isinstance(v, dict):
                output_mc[k] = np.append(output_mc[k], np.array([v]), axis=0)
            else:
                self._append_output_mc(output_mc[k], v)

    # Save output from MC runs
    def _save_output_mc(self):
        if self._output_mc is None:
            self._output_mc = self._init_output_mc(self._output)
        else:
            self._append_output_mc(self._output_mc, self._output)

    # Monte carlo runs
    def _run_mc(self, reps=None, end=None, dt=None,
                start_time=None, start_date=None, init=None):
        # First apply initial conditions from init dict
        if init is not None:
            self._init_cond(init)

        # Override for any of the following run parameters
        if reps is not None:
            self._push_init('_reps', reps)

        if end is not None:
            self._push_init('_end', end)

        if dt is not None:
            self._push_init('_dt', dt)

        if start_time is not None:
            self._push_init('_t', start_time)

        if start_date is not None:
            self_push_init('_date', start_date)

        # Reset mc output
        self._reset_output_mc()

        # Run all reps and save mc output
        for n in range(int(self._reps())):
            self._run()
            self._save_output_mc()
