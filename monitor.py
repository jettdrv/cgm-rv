import json
import argparse
import rtamt


#funzione per valutare le specifiche esprimibili in STL. 
#ritorna una lista di violazioni con il relativo tempo e robustezza
def evaluate_specSTL(name, formula, signals, time):
    spec = rtamt.StlDenseTimeSpecification()
    spec.name=name
    for var in signals.keys():
        spec.declare_var(var, 'float')
    spec.spec = formula
    spec.parse()

    args=[]
    for var, values in signals.items():
        args.append([var, list(zip(time, values))])

    robustness = spec.evaluate(*args)

    violations = []
    for t, r in robustness:
        if r<0:
            violations.append({
                'time': t,
                'robustness': round(r, 5)
            })

    return robustness, violations

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('filename')
    args = parser.parse_args()

    events=[]
    with open(args.filename, 'r') as f:
        events=json.load(f)  

    #creazione dei segnali
    time = [e['time_min'] for e in events]
    diff_prev_time = [e['diff_prev_time'] for e in events]
    cgm = [e['cgm'] for e in events]
    roc = [e['roc'] for e in events]
    cgm_predicted=[e['cgm_predicted'] for e in events]
    alarm_delay=[float(e['alarm_delay']) for e in events]
    alarm_hypo=[float(e['alarm_hypo']) for e in events]
    alarm_out_of_range=[float(e['alarm_out_of_range']) for e in events]



    results = {}


    #---------------------------------------SENSORE CGM----------------------------------------------------------------------------------------
    #---------------------------------------------------------------------------------------------------------------------------------------
 
    #----------Specifica 1: segnalazione al sistema per i gap tra 10-15 minuti, avviso al paziente per gap maggiori di 20 minuti-------------------------4
    robustness, v = evaluate_specSTL(
        name      = 'spec_1_delay',
        formula   = 'always[0:0](diff_prev_time > 20.0 implies eventually[0:0](alarm_delay >= 1.0))',
        signals   = {'diff_prev_time': diff_prev_time, 'alarm_delay': alarm_delay},
        time      = time
    )
    results['spec_1_delay'] = v
    #----------Specifica 2: un ritardo di 30 minuti indica il fallimento del sensore. non si deve mai verificare------------------------------------------
    robustness, v = evaluate_specSTL(
        name      = 'spec_2_error',
        formula   = 'always[0:0](diff_prev_time < 30.0)',
        signals   = {'diff_prev_time': diff_prev_time},
        time      = time
    )
    results['spec_2_error'] = v
   
    #----------Specifica 3: il sensore può effettuare delle letture accurate solo nell'intervallo 40-400 mg--------------------
    robustness, v = evaluate_specSTL(
        name      = 'spec_3_range_cgm',
        formula   = 'always[0:0](cgm >= 40 and cgm <= 400)',
        signals   = {'cgm': cgm},
        time      = time
    )
    results['spec_3_range_cgm'] = v
    
    
    # ---------Specifica 4: niente sbalzi < 25 mg/dL  tra due campioni successivi------------------------------------ 
    robustness, v = evaluate_specSTL(
        name      = 'spec_4_cgm_jump',
        formula   = 'always[0:0](historically[5:5] cgm - cgm <= 25.0 and cgm<=historically[5:5] cgm + 25.0)',
        signals   = {'cgm': cgm},
        time      = time
    )
    results['spec_4_cgm_jump'] = v

    #---------Specifica 5: controllo allarme range personale------------------------------------ 
    #per adesso di default 70-180. 
    #rise not implemented in dense time stl
    robustness, v = evaluate_specSTL(
        name      = 'spec_5_alarm_range',
        formula   = ' always[0:0]((cgm > 180 or cgm < 70) implies eventually[0:5](alarm_out_of_range >=1.0))',
        signals   = {'cgm': cgm, 'alarm_out_of_range': alarm_out_of_range},
        time      = time
    )
    results['spec_5_alarm_range'] = v

    # ---------Specifica 6: allarme ipoglicemia imminente -------------------------------------------
    
    robustness, v = evaluate_specSTL(
        name      = 'spec_6_alarm,_ipo',
        formula   = 'always[0:0] (cgm_predicted<70 implies eventually[0:5] (alarm_hypo >= 1.0)) ',
        signals   = {'cgm_predicted': cgm_predicted, "alarm_hypo":alarm_hypo},
        time      = time
    )
    results['spec_6_alarm_ipo'] = v


    #--------------------------INSULIN PUMP-----------------------------------------------------------------------------------------------------
    #--------------------------------------------------------------------------------------------------------------------------------------
    
    
    #-----Risultati-----------------------
    print("\n Risultati \n")
    for spec_name, violations in results.items():
        if violations:
            print(f"{spec_name}: {len(violations)} violazioni")
            for v in violations:
                if 'robustness' in v:
                    print(f"   t={v['time']} min | robustness={v['robustness']}")
        else:
            print(f"{spec_name}: nessuna violazione")

    # ---Salvataggio risultati--------------------------------------
    with open('results.json', 'w') as f:
        json.dump(results, f, indent=4)


    
if __name__ == '__main__':
    main()