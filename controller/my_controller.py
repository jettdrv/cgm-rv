from .base import Controller
from .base import Action
import numpy as np
import pandas as pd
import pkg_resources
import logging

logger = logging.getLogger(__name__)
CONTROL_QUEST = pkg_resources.resource_filename('simglucose',
                                                'params/Quest.csv')
PATIENT_PARA_FILE = pkg_resources.resource_filename(
    'simglucose', 'params/vpatient_params.csv')


class MyController(Controller):
    """
    This is a Basal-Bolus Controller that is typically practiced by a Type-1
    Diabetes patient. The performance of this controller can serve as a
    baseline when developing a more advanced controller.
    """
    def __init__(self, target=140):
        self.quest = pd.read_csv(CONTROL_QUEST)
        self.patient_params = pd.read_csv(PATIENT_PARA_FILE)
        self.target = target
        self._suspend_timer = 0


    def policy(self, observation, reward, done, **kwargs):
        sample_time = kwargs.get('sample_time', 1)
        pname = kwargs.get('patient_name')
        meal = kwargs.get('meal')  # unit: g/min
        

        action = self._bb_policy(pname, meal, observation.CGM, observation.cgm_predicted, observation.roc, sample_time)
        return action
    
    def _bb_policy(self, name, meal, glucose, cgm_predicted, roc,  env_sample_time):

        """
        Helper function to compute the basal and bolus amount.

        The basal insulin is based on the insulin amount to keep the blood
        glucose in the steady state when there is no (meal) disturbance. 
               basal = u2ss (pmol/(L*kg)) * body_weight (kg) / 6000 (U/min)
        
        The bolus amount is computed based on the current glucose level, the
        target glucose level, the patient's correction factor and the patient's
        carbohydrate ratio.
               bolus = ((carbohydrate / carbohydrate_ratio) + 
                       (current_glucose - target_glucose) / correction_factor)
                       / sample_time
        NOTE the bolus computed from the above formula is in unit U. The
        simulator only accepts insulin rate. Hence the bolus is converted to
        insulin rate.
        """
        if any(self.quest.Name.str.match(name)):
            quest = self.quest[self.quest.Name.str.match(name)]
            params = self.patient_params[self.patient_params.Name.str.match(
                name)]
            u2ss = params.u2ss.values.item()  # unit: pmol/(L*kg)
            BW = params.BW.values.item()  # unit: kg
        else:
            quest = pd.DataFrame([['Average', 1 / 15, 1 / 50, 50, 30]],
                                 columns=['Name', 'CR', 'CF', 'TDI', 'Age'])
            u2ss = 1.43  # unit: pmol/(L*kg)
            BW = 57.0  # unit: kg


        basal = u2ss * BW / 6000  # unit: U/min

        #low-glucose suspend
        if (glucose < 105.0 and cgm_predicted < 85):
            if self._suspend_timer <= 0:
                logger.info(f'Low glucose suspend: cgm= {glucose}, cgm_predicted={cgm_predicted}')
                self._suspend_timer =120
      
        
        if self._suspend_timer > 0 :
            if glucose >= 85 and cgm_predicted >=105:
                logger.info(f'Exit Low glucose suspend: cgm= {glucose}, cgm_predicted={cgm_predicted}')
                self._suspend_timer = 0
            
            else:
                self._suspend_timer -= env_sample_time
                logger.info(f'LGS active. Suspend timer: {self._suspend_timer} min remaining')
            basal = 0

        if meal > 0:
            logger.info('Calculating bolus ...')
            logger.info(f'Meal = {meal} g/min')
            logger.info(f'glucose = {glucose}')
            bolus = (
                (meal * env_sample_time) / quest.CR.values + (glucose > 150) *
                (glucose - self.target) / quest.CF.values).item()  # unit: U
        else:
            bolus = 0  # unit: U

        # This is to convert bolus in total amount (U) to insulin rate (U/min).
        # The simulation environment does not treat basal and bolus
        # differently. The unit of Action.basal and Action.bolus are the same
        # (U/min).
        bolus = bolus / env_sample_time  # unit: U/min

        logger.info(f'roc={roc}, cgm_predicted={cgm_predicted}, basal={basal}, bolus={bolus}')
        return Action(basal=basal, bolus=bolus)


    def reset(self):
        self._suspend_timer = 0
