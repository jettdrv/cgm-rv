import csv
import json
import argparse
import numpy as np
from datetime import datetime



class Event:
    def __init__(self, timestamp, time_min, bg, cgm, cho, insulin, roc, cgm_predicted, lbgi, hbgi, risk):
        self.timestamp = timestamp
        self.time_min = time_min
        self.bg =bg
        self.cgm = cgm
        self.cho = cho
        self.roc = roc 
        self.cgm_predicted = cgm_predicted
        self.insulin = insulin
        self.lbgi = lbgi
        self.hbgi = hbgi
        self.risk = risk

        #dati derivati
        self.lgs_active= None #timer per la sospensione dell'insulina
        self.alarm_delay=None
        self.alarm_hypo=None
        self.alarm_out_of_range=None
        self.real_roc= None

    def set_lgs_active(self, lgs):
        self.lgs_active = lgs
        
    def set_alarm_delay(self, prev_event):
        self.alarm_delay= self.time_min - prev_event.time_min >20

    def set_alarm_hypo(self):
        self.alarm_hypo = (self.cgm < 70 or self.cgm_predicted < 70)
    
    def set_alarm_out_of_range(self, low, high):
        self.alarm_out_of_range= (self.cgm < low  or self.cgm > high)
    
    def calc_real_roc(self, bg_history, sample_time):
        history = bg_history[-4:]  
        n = len(history)
        if n < 2:
            self.real_roc = 0.0
            return
        
        times = np.array([i * sample_time for i in range(n)])
        values = np.array(history)
        self.real_roc = round(np.polyfit(times, values, 1)[0], 6)
        

    

    def toDict(self):
        return {
            "timestamp": str(self.timestamp),
            "time_min": self.time_min,
            "bg": self.bg,
            "cgm": self.cgm,
            "cho": self.cho,
            "insulin": self.insulin,
            "roc": self.roc,
            "cgm_predicted": self.cgm_predicted,

            "lbgi": self.lbgi,
            "hbgi": self.hbgi,
            "risk": self.risk,
            
            "lgs_active": self.lgs_active,

            "alarm_delay": self.alarm_delay,
            "alarm_hypo": bool(self.alarm_hypo),
            "alarm_out_of_range": bool(self.alarm_out_of_range),
            "real_roc": self.real_roc

        }


class ExecutionTrace:
    def __init__(self, low, high):
        self.events = []
        self.low = low
        self.high=high
        self._lgs_timer=0


    def add_event(self, event, low, high, sample_time):
        bg_history = [e.bg for e in self.events]
        bg_history.append(event.bg)
        event.calc_real_roc(bg_history, sample_time)

        if self.events:
            i = len(self.events)
            event.set_alarm_delay(self.events[-1])
            event.set_alarm_hypo()
            event.set_alarm_out_of_range(self.low, self.high)
        else:
            event.alarm_delay=False
            event.alarm_hypo=event.cgm<70
            event.alarm_out_of_range= (event.cgm< low or event.cgm > high)

            

        if event.cgm < 105.0 and event.cgm_predicted < 85.0:
            if self._lgs_timer <= 0:                
                self._lgs_timer=120 
                
        if self._lgs_timer > 0: 
            if event.cgm >= 105.0 and event.cgm_predicted >= 85:
                self._lgs_timer = 0
            else:
                self._lgs_timer -= sample_time
        if self._lgs_timer < 0:
            self._lgs_timer = 0

        active = self._lgs_timer > 0
        event.set_lgs_active(active)
        
        self.events.append(event)
    
    def convert_json(self, filepath):
        with open(filepath, 'w') as f:
            json.dump([e.toDict() for e in self.events], f, indent=4)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('filename')
    parser.add_argument('--low', type=float, default=70.0)
    parser.add_argument('--high', type=float, default=180.0)
    parser.add_argument('--time', type=int, default=5)
    parser.add_argument('--output',  default='eventi')


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
                bg = float(row["BG"]),
                cgm=float(row["CGM"]),
                cho=float(row["CHO"]),
                insulin=float(row["insulin"]),
                roc=float(row["roc"]),
                cgm_predicted=float(row["cgm_predicted"]),
                lbgi=float(row["LBGI"]),
                hbgi=float(row["HBGI"]),
                risk=float(row["Risk"])
            )

            trace.add_event(event, args.low, args.high, args.time)

    trace.convert_json(f'{args.output}.json')


if __name__ == '__main__':
    main()