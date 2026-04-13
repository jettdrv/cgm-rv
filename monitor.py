import json
import argparse
import rtamt
import math
import matplotlib.pyplot as plt
import numpy as np
import os
import matplotlib

if not os.path.exists('grafici'):
    os.makedirs('grafici')

#funzione di servizio per il salvataggio dei risultati

def process_results(name, robustness, results):

    violations = [{'time': t, 'robustness': round(r, 5)} for t, r in robustness if r < 0]
    n_violations = len(violations)
    

    results[name] = {
        "full_trace": robustness,
        "violation_count": n_violations,
        "pass": n_violations == 0,
        "violations_details": violations 
    }


#funzione di servizio per la stampa dei risultati formattati in una tabella
def print_results(results):
    print("\n" + "="*80)
    print(f"{'SPECIFICA':<25} | {'STATO':<10} | {'DETTAGLI'}")
    print("-"*80)
    
    for name, data in results.items():
        status = "PASS" if data["pass"] else "FAIL"
        
        if "lower_bound" in data:
            dettagli = f"LB: {data['lower_bound']:.4f} (Soglia: {data['threshold']}) | N: {data['n_total']}"
        else:
            dettagli = f"Violazioni: {data['violation_count']}"
            
        print(f"{name:<25} | {status:<10} | {dettagli}")
    
    print("="*80 + "\n")


#funzione di servizio per la costruzione dei grafi di robustezza
def graph_results(time, cgm, bg, robustness, req_name, error):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True, gridspec_kw={'height_ratios': [2, 1]})

    ax1.plot(time, bg, label='Blood Glucose (BG)', color='black', linewidth=2)
    ax1.plot(time, cgm, label='CGM Sensor', color='blue', linestyle='--', alpha=0.8)
    
  
    upper_bound = [b + (error*0.01 * b) for b in bg]
    lower_bound = [b - (error*0.01 * b) for b in bg]
    ax1.fill_between(time, lower_bound, upper_bound, color='gray', alpha=0.2, label=f'{error}% Tolerance Band')
    
    ax1.set_ylabel('Glucose (mg/dL)')
    ax1.set_title(f'Validation of {req_name}')
    ax1.legend(loc='upper right')
    ax1.grid(True, alpha=0.3)

    t_rob = [r[0] for r in robustness]
    v_rob = [r[1] for r in robustness]
    
    ax2.step(t_rob, v_rob, where='post', color='red', label='STL Robustness')
    ax2.axhline(0, color='black', linestyle='-', linewidth=1) 
    
    ax2.fill_between(t_rob, v_rob, 0, where=(np.array(v_rob) < 0), color='red', alpha=0.3)
    
    ax2.set_ylabel('Robustness')
    ax2.set_xlabel('Time (min)')
    ax2.grid(True, alpha=0.3)
    ax2.legend(loc='upper right')

    plt.tight_layout()
    plt.savefig(f'grafici/graph_{req_name}.png', dpi=300)
    plt.close()



#funzione per valutare le specifiche esprimibili in STL. 
#ritorna una lista di violazioni con il relativo tempo e robustezza

def evaluate_spec(name, formula, signals, time, mode='dense', sample_time=5):
    if mode=='dense':
        return evaluate_spec_dense(name, formula, signals, time)

    elif mode =='discrete':
        return evaluate_spec_discrete(name, formula, signals, time, sample_time)
    else:
        raise ValueError("Usa 'dense' o 'discrete' ")

#specifiche tempo discreto
def evaluate_spec_discrete(name, formula, signals, time, sample_time=5):
    spec = rtamt.StlDiscreteTimeSpecification()
    
    spec.name=name
    for var in signals.keys():
        spec.declare_var(var, 'float')
    spec.spec = formula
    spec.sampling_period = sample_time * 60
    spec.parse()

    dataset = {'time': time}
    for var, value in signals.items():
        dataset[var] = value

    robustness = spec.evaluate(dataset)
    return robustness

#specifiche tempo denso
def evaluate_spec_dense(name, formula, signals, time):
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
    return robustness


def calculate_lower_bound(success, total):
    if total == 0:
        return 0
    p= success / total
    z = 1.645  #95% one sided
    return p - z * math.sqrt((p * (1 - p)) / total)

def verify_clinical_req(name, robustness, filter, threshold, results, time, cgm, bg, error=20):
    n_total = 0 
    n_success = 0

    for i in range(len(robustness)):
        if filter[i]:
            n_total+=1
            if robustness[i][1] >= 0:
                n_success += 1
    lb = calculate_lower_bound(n_success, n_total)
    passed = lb >= threshold
    results[name] = {
        "full_trace": robustness,
        "n_total": n_total,
        "n_success": n_success,
        "lower_bound": round(lb, 4),
        "threshold": threshold,
        "pass": passed
    }
    graph_results(time, cgm, bg, robustness, name, error)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('filename')
    parser.add_argument('-t', '--time', type=int, default=5, help='Intervallo di campionamento, default 5 minuti')
    parser.add_argument('-b', '--bodyweight', type=float, default=111.1, help='Peso del paziente')
    parser.add_argument('-T', '--target', type=float, default=140.0, help='BG target')
    parser.add_argument('-r', '--cr', type=float, default=8, help='Rapporto insulina/carboidrati')
    parser.add_argument('-f', '--cf', type=float, default=9.21276345633, help='Fattore di correzione')
    parser.add_argument('-d', '--tdi', type=float, default=57.86877688, help='Dose giornaliera totale di insulina')
    parser.add_argument('-u', '--u2ss', type=float, default=1.23270240324, help='Concentrazione di insulina allo stato stazionario')

    args = parser.parse_args()

    sample_time = args.time


    events=[]
    with open(args.filename, 'r') as f:
        events=json.load(f)  

    #creazione dei segnali
    time = [e['time_min'] for e in events]
    cgm = [e['cgm'] for e in events]
    bg = [e['bg'] for e in events]
    cho = [e['cho'] for e in events]
    insulin = [e['insulin'] for e in events]
    roc = [e['roc'] for e in events]
    real_roc=[e['real_roc'] for e in events]
    cgm_predicted=[e['cgm_predicted'] for e in events]
    alarm_delay=[float(e['alarm_delay']) for e in events]
    alarm_hypo=[float(e['alarm_hypo']) for e in events]
    alarm_out_of_range=[float(e['alarm_out_of_range']) for e in events]
    lgs_active=[float(e['lgs_active']) for e in events]


    basal_list = []

    for e in events:

        basal=args.u2ss  * args.bodyweight / 6000
        basal_list.append(float(basal))


    bolus_list = []
    for e in events:
        current_cho=e['cho']
        current_glucose=e['cgm']
        if current_cho > 0:
            bolus = ((current_cho * args.time) / args.cr + (current_glucose > 150) *(current_glucose - args.target) / args.cf) # unit: U
            bolus_list.append(float(bolus))
        else:
            bolus_list.append(0.0)


    results = {}


    #---------------------------------------SENSORE CGM----------------------------------------------------------------------------------------
    #---------------------------------------------------------------------------------------------------------------------------------------
 
    #----------Specifica 1: segnalazione al sistema per i gap tra 10-15 minuti, avviso al paziente per gap maggiori di 20 minuti-------------------------
    robustness = evaluate_spec(
        name      = 's_spec_1_delay',
        formula   = 'always((timestamp > prev timestamp + 20.0 ) implies (alarm_delay > 0.5))',
        signals   = {'alarm_delay': alarm_delay, 'timestamp': time},
        time      = time,
        mode      ='discrete',
        sample_time= sample_time
    )
    process_results('s_spec_1_delay', robustness, results)
    #----------Specifica 2: un ritardo di 30 minuti indica il fallimento del sensore. non si deve mai verificare------------------------------------------
    robustness    = evaluate_spec(
        name      = 's_spec_2_error',
        formula   = 'always(timestamp  < prev timestamp + 30.0)',
        signals   = {'timestamp': time},
        time      = time,
        mode      = 'discrete'
    )
    process_results('s_spec_2_error', robustness, results)
   
    #----------Specifica 3: il sensore può effettuare delle letture accurate solo nell'intervallo 40-400 mg--------------------
    robustness    = evaluate_spec(
        name      = 's_spec_3_range_cgm',
        formula   = 'always(cgm >= 40.0 and cgm <= 400.0)',
        signals   = {'cgm': cgm},
        time      = time
    )
    process_results('s_spec_3_range_cgm', robustness, results)
    
    # ---------Specifica 4: niente sbalzi < 25 mg/dL  tra due campioni successivi------------------------------------ 
    robustness    = evaluate_spec(
        name      = 's_spec_4_cgm_jump',
        formula   = 'always(prev cgm  <= 25.0 + cgm and prev cgm - 25.0 <=  cgm )',
        signals   = {'cgm': cgm},
        time      = time,
        mode      ='discrete'
    )
    process_results('s_spec_4_cgm_jump', robustness, results)

    #---------Specifica 5: controllo allarme range personale------------------------------------ 
    #per adesso di default 70-180. 
    robustness    = evaluate_spec(
        name      = 's_spec_5_alarm_range',
        formula   = ' always((cgm > 180.0 or cgm < 70.0) implies eventually[0:5](alarm_out_of_range > 0.5))',
        signals   = {'cgm': cgm, 'alarm_out_of_range': alarm_out_of_range},
        time      = time
    )
    process_results('s_spec_5_alarm_range', robustness, results)

    # ---------Specifica 6: allarme ipoglicemia imminente -------------------------------------------
    
    robustness    = evaluate_spec(
        name      = 's_spec_6_alarm_ipo',
        formula   = 'always(cgm_predicted < 70.0 implies eventually[0:5] (alarm_hypo > 0.5)) ',
        signals   = {'cgm_predicted': cgm_predicted, "alarm_hypo":alarm_hypo},
        time      = time
    )

    process_results('s_spec_6_alarm_ipo', robustness, results)



    #================================================================================================
    # ------CLINICAL REQUIREMENTS -----------------------------------------------
    # =============================================================================

    #---------------Requirement 1 ---------------------------------------------
    robustness    = evaluate_spec(
        name      = 'less_70_15',
        formula   = 'always[0,0](cgm < 70.0 implies abs(cgm - bg) <= 15.0)',
        signals   = {'cgm': cgm, "bg":bg},
        time      = time,
        mode      ='discrete'
    )

    verify_clinical_req('less_70_15', robustness, [c < 70.0 for c in cgm], 0.85, results, time, cgm, bg, error=15)

    #---------------------Requirement 2---------------------------------------

    robustness    = evaluate_spec(
        name      = 'between_70_180_15',
        formula   = 'always[0,0](((cgm >= 70.0) and (cgm <= 180.0)) implies (abs(cgm - bg) <= 15.0))',
        signals   = {'cgm': cgm, "bg":bg},
        time      = time,
        mode      ='discrete'
    )

    verify_clinical_req('between_70_180_15', robustness, [70.0 <= c <= 180.0 for c in cgm], 0.70, results, time, cgm, bg, error=15)
    #---------------------Requirement 3---------------------------------------

    robustness    = evaluate_spec(
        name      = 'greater_than_180_15',
        formula   = 'always[0,0]((cgm > 180.0) implies (abs(cgm - bg) <= 15.0))',
        signals   = {'cgm': cgm, "bg":bg},
        time      = time,
        mode      ='discrete'
    )

    verify_clinical_req('greater_than_180_15', robustness, [ c > 180.0 for c in cgm], 0.80, results, time, cgm, bg, error=15)
    #---------------------Requirement 4---------------------------------------

    robustness    = evaluate_spec(
        name      = 'less_70_40',
        formula   = 'always[0,0](cgm < 70.0 implies abs(cgm - bg) <= 40.0)',
        signals   = {'cgm': cgm, "bg":bg},
        time      = time,
        mode      ='discrete'
    )

    verify_clinical_req('less_70_40', robustness, [ c < 70.0 for c in cgm], 0.98, results, time, cgm, bg, error=40)
    #---------------------Requirement 5---------------------------------------

    robustness    = evaluate_spec(
        name      = 'between_70_180_40',
        formula   = 'always[0,0](((cgm >= 70.0) and (cgm <= 180.0)) implies (abs(cgm - bg) <= 40.0))',
        signals   = {'cgm': cgm, "bg":bg},
        time      = time,
        mode      ='discrete'
    )

    verify_clinical_req('between_70_180_40', robustness, [70.0 <=c <= 180.0 for c in cgm], 0.99, results, time, cgm, bg, error= 40)

    #---------------------Requirement 6---------------------------------------

    robustness     = evaluate_spec(
        name      = 'greater_than_180_40',
        formula   = 'always[0,0]((cgm > 180.0) implies (abs(cgm - bg) <= 40.0))',
        signals   = {'cgm': cgm, "bg":bg},
        time      = time,
        mode      ='discrete'
    )

    verify_clinical_req('greater_than_180_40', robustness, [c > 180.0 for c in cgm], 0.99, results, time, cgm, bg, error=40)
    #---------------------Requirement 7---------------------------------------

    robustness    = evaluate_spec(
        name      = 'interval_20',
        formula   = 'always[0,0]((cgm >= 40 and cgm <= 400 ) implies (abs(cgm - bg) <= 20.0))',
        signals   = {'cgm': cgm, "bg":bg},
        time      = time,
        mode      ='discrete'
    )

    verify_clinical_req('interval_20', robustness, [40.0 <=c <= 400.0 for c in cgm], 0.87, results, time, cgm, bg, error=20)

    #---------------------Requirement 8---------------------------------------

    robustness    = evaluate_spec(
        name      = 'ipo_not_iper',
        formula   = 'always[0,0]((cgm < 70.0) implies not(bg > 180.0))',
        signals   = {'cgm': cgm, "bg":bg},
        time      = time,
        mode      ='discrete'
    )
    process_results('ipo_not_iper', robustness, results)

    #---------------------Requirement 9---------------------------------------

    robustness    = evaluate_spec(
        name      = 'iper_not_ipo',
        formula   = 'always[0,0]((cgm > 180.0) implies not(bg < 70.0))',
        signals   = {'cgm': cgm, "bg":bg},
        time      = time,
        mode      ='discrete'
    )
    process_results('iper_not_ipo', robustness, results)
    #---------------------Requirement 10---------------------------------------

    robustness    = evaluate_spec(
        name      = 'roc_pos',
        formula   = 'always[0,0]((roc > 1.0) implies not(real_roc < -2.0))',
        signals   = {'roc': roc, "real_roc":real_roc},
        time      = time,
        mode      ='discrete'
    )

    verify_clinical_req('roc_pos', robustness, [r > 1.0 for r in roc], 0.99, results, time, cgm, bg)
    #---------------------Requirement 11---------------------------------------

    robustness    = evaluate_spec(
        name      = 'roc_neg',
        formula   = 'always[0,0]((roc < -1.0) implies not(real_roc > 2.0))',
        signals   = {'roc': roc, "real_roc":real_roc},
        time      = time,
        mode      ='discrete'
    )

    verify_clinical_req('roc_neg', robustness, [r < -1.0 for r in roc], 0.99, results, time, cgm, bg)

        

    #========================================================================================================================================
    #--------------------------INSULIN PUMP-------------------------------------------------------------------------------------------------
    #--------------------------------------------------------------------------------------------------------------------------------------

   
    #----------Specifica 1: Insulina in modo continuo se cgm>70.0 e cgm_predicted > 85.0------------------------------------------------------------------
    #
    robustness    = evaluate_spec(
        name      = 'ip_spec_1_insulin',
        formula   = 'always[0:0](((cgm > 105.0 and cgm_predicted > 85.0) and lgs_active < 0.5) implies eventually[0:5]insulin > 0.001)',
        signals   = {'cgm': cgm, "cgm_predicted":cgm_predicted, 'insulin': insulin, 'lgs_active': lgs_active},
        time      = time
    )
    process_results('ip_spec_1_insulin', robustness, results)

    
    #----------Specifica 2: Low glucose suspend-------------------------------------------------------------------
    robustness    = evaluate_spec(
        name      = 'ip_spec_2_suspend',
        formula   = 'always((cgm < 105.0 and cgm_predicted < 85.0) implies (lgs_active >0.5  U[5:120](cgm > 85.0 and cgm_predicted > 105.0)))',
        signals   = {'cgm': cgm, "cgm_predicted": cgm_predicted, "insulin": insulin, "lgs_active": lgs_active},
        time      = time,

    )
    process_results('ip_spec_2_suspend', robustness, results)

#.............Specifica 3----------------------------------------

    robustness    = evaluate_spec(
        name      = 'ip_spec_3_suspend',
        formula   = 'always[0:0](historically[0:6] lgs_active > 0.5 implies insulin <= 0.00001)',
        signals   = {'cgm': cgm, "cgm_predicted": cgm_predicted, "insulin": insulin, "lgs_active": lgs_active},
        time      = time,

    )
    process_results('ip_spec_3_suspend', robustness, results)



    #----------Specifica 4: Low glucose suspend-------------------------------------------------------------------
    robustness    = evaluate_spec(
        name      = 'ip_spec_4_suspend',
        formula   = 'always(lgs_active > 0.5 implies F[0:120] lgs_active < 0.5)',
        signals   = {'cgm': cgm, "cgm_predicted": cgm_predicted, "insulin": insulin, "lgs_active": lgs_active},
        time      = time,

    )
    process_results('ip_spec_4_suspend', robustness, results)

    #----------Specifica 5: Low glucose suspend-------------------------------------------------------------------
    robustness    = evaluate_spec(
        name      = 'ip_spec_5_suspend',
        formula   = 'always((H[0:60] lgs_active > 0.5 and cgm >= 105.0 and cgm_predicted >= 85) implies (F lgs_active < 0.5 and insulin > 0.0001))',
        signals   = {'cgm': cgm, "cgm_predicted": cgm_predicted, "insulin": insulin, "lgs_active": lgs_active},
        time      = time,

    )
    process_results('ip_spec_5_suspend', robustness, results)

#===============================================================================================================

    #----------Specifica 6: Insulina basale se cgm e cgm_predicted > 70.0 e nessun pasto , da corso-------------------------------------------------------------------
    robustness    = evaluate_spec(
        name      = 'ip_spec_6_basal',
        formula   = 'always((cgm > 105.0 and cgm_predicted > 85.0 and cho<=0.001) implies eventually[0:5](insulin <= basal))',
        signals   = {'cgm': cgm, 'cgm_predicted':cgm_predicted, 'insulin': insulin, 'cho': cho, 'basal': basal_list},
        time      = time
    )
    process_results('ip_spec_6_basal', robustness, results)



    #----------Specifica 7: Dose corretta di insulina anche in caso di pasto-------------------------------------------------------------------
    robustness    = evaluate_spec(
        name      = 'ip_spec_7_bolus',
        formula   = 'always((cho > 0.0 and historically[270:3600]cho <= 0.0) implies eventually[0:5](insulin <= bolus + basal))',
        signals   = {'cgm': cgm, "cgm_predicted":cgm_predicted, "insulin": insulin, "cho": cho, 'bolus': bolus_list, 'basal': basal_list}, 
        time      = time
    )
    process_results('ip_spec_7_bolus', robustness, results)

    #----------risultati--------------------------------------------
    print_results(results)

    # ---Salvataggio risultati--------------------------------------
    with open('results.json', 'w') as f:
        json.dump(results, f, indent=4)


    
if __name__ == '__main__':
    main()