import csv
import json
import argparse
import numpy as np
from datetime import datetime

class Event:
    def __init__(self, timestamp, time_min, cgm, cho, insulin, lbgi, hbgi, risk):
        self.timestamp = timestamp
        self.time_min = time_min
        self.cgm = cgm
        self.cho = cho
        self.insulin = insulin
        self.lbgi = lbgi
        self.hbgi = hbgi
        self.risk = risk

        #dati derivati
        self.diff_prev_time = None
        self.roc = None
        self.cgm_predicted=None
        self.alarm_hypo=None
        self.alarm_out_of_range=None

    def set_diff_prev_time(self, prev_event):
        self.diff_prev_time= self.time_min - prev_event.time_min

    def set_roc(self, times, glucoses, i):
        start = max(0, i - 4)
        t = times[start:i]
        g = glucoses[start:i]
        if len(t) < 2:
            self.roc=0.0
            return
        coeffs = np.polyfit(t, g, 1)
        self.roc = coeffs[0]

    def set_cgm_predicted(self):
        self.cgm_predicted= self.cgm + self.roc * 30

    def set_alarm_hypo(self):
        self.alarm_hypo = (self.cgm < 70 or self.cgm_predicted < 70)
    
    def set_alarm_out_of_range(self, low, high):
        self.alarm_out_of_range= (self.cgm < low  or self.cgm > high)

    

    def toDict(self):
        return {
            "timestamp": str(self.timestamp),
            "time_min": self.time_min,
            "cgm": self.cgm,
            "cho": self.cho,
            "insulin": self.insulin,
            "lbgi": self.lbgi,
            "hbgi": self.hbgi,
            "risk": self.risk,
            "roc": self.roc,
            "diff_prev_time": self.diff_prev_time,
            "cgm_predicted": self.cgm_predicted,
            "alarm_hypo": bool(self.alarm_hypo),
            "alarm_out_of_range": bool(self.alarm_out_of_range)

        }


class ExecutionTrace:
    def __init__(self, low, high):
        self.events = []
        self.low = low
        self.high=high
        self._times=[]
        self._glucoses=[]


    def add_event(self, event, low, high):
        if self.events:
            i = len(self.events)
            event.set_diff_prev_time(self.events[-1])
            event.set_roc(self._times, self._glucoses, i)
            event.set_cgm_predicted()
            event.set_alarm_hypo()
            event.set_alarm_out_of_range(self.low, self.high)
        else:
            event.diff_prev_time= 0.0
            event.roc=0.0
            event.cgm_predicted=event.cgm
            event.alarm_hypo=event.cgm<70
            event.alarm_out_of_range= (event.cgm< low or event.cgm > high)
        self.events.append(event)
        self._times.append(event.time_min)
        self._glucoses.append(event.cgm)
    
    def convert_json(self, filepath):
        with open(filepath, 'w') as f:
            json.dump([e.toDict() for e in self.events], f, indent=4)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('filename')
    parser.add_argument('--low', type=float, default=70.0)
    parser.add_argument('--high', type=float, default=180.0)

    args = parser.parse_args()

    trace = ExecutionTrace(low=args.low, high= args.high)

    with open(args.filename, newline="") as f:
        reader = csv.DictReader(f)
        start_time=None
        for row in reader:
            t = datetime.strptime(row["Time"], "%Y-%m-%d %H:%M:%S")
            if start_time is None:
                start_time = t
            time_min = (t - start_time).total_seconds() / 60

            event=Event(
                timestamp=t,
                time_min=time_min,
                cgm=float(row["CGM"]),
                cho=float(row["CHO"]),
                insulin=float(row["insulin"]),
                lbgi=float(row["LBGI"]),
                hbgi=float(row["HBGI"]),
                risk=float(row["Risk"])
            )

            trace.add_event(event, args.low, args.high)

    trace.convert_json('eventi.json')


if __name__ == '__main__':
    main()