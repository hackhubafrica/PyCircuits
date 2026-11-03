/* Main Simulation File */

#if defined(__cplusplus)
extern "C" {
#endif

#include "MassSpringDamperPlant_model.h"
#include "simulation/solver/events.h"
#include "simulation/arrayIndex.h"

/* FIXME these defines are ugly and hard to read, why not use direct function pointers instead? */
#define prefixedName_performSimulation MassSpringDamperPlant_performSimulation
#define prefixedName_updateContinuousSystem MassSpringDamperPlant_updateContinuousSystem
#include <simulation/solver/perform_simulation.c.inc>

#define prefixedName_performQSSSimulation MassSpringDamperPlant_performQSSSimulation
#include <simulation/solver/perform_qss_simulation.c.inc>


/* dummy VARINFO and FILEINFO */
const VAR_INFO dummyVAR_INFO = omc_dummyVarInfo;

int MassSpringDamperPlant_input_function(DATA *data, threadData_t *threadData)
{
  
  return 0;
}

int MassSpringDamperPlant_input_function_init(DATA *data, threadData_t *threadData)
{
  
  return 0;
}

int MassSpringDamperPlant_input_function_updateStartValues(DATA *data, threadData_t *threadData)
{
  
  return 0;
}

int MassSpringDamperPlant_inputNames(DATA *data, char ** names){
  
  return 0;
}

int MassSpringDamperPlant_data_function(DATA *data, threadData_t *threadData)
{
  return 0;
}

int MassSpringDamperPlant_dataReconciliationInputNames(DATA *data, char ** names){
  
  return 0;
}

int MassSpringDamperPlant_dataReconciliationUnmeasuredVariables(DATA *data, char ** names)
{
  
  return 0;
}

int MassSpringDamperPlant_output_function(DATA *data, threadData_t *threadData)
{
  
  return 0;
}

int MassSpringDamperPlant_setc_function(DATA *data, threadData_t *threadData)
{
  
  return 0;
}

int MassSpringDamperPlant_setb_function(DATA *data, threadData_t *threadData)
{
  
  return 0;
}


/*
equation index: 34
type: SIMPLE_ASSIGN
$DER.mass.s = -damper.v_rel
*/
void MassSpringDamperPlant_eqFunction_34(DATA *data, threadData_t *threadData)
{
  const int equationIndexes[2] = {1,34};
  (data->localData[0]->realVars[data->simulationInfo->realVarsIndex[9]] /* der(mass.s) DUMMY_DER */) = (-(data->localData[0]->realVars[data->simulationInfo->realVarsIndex[3]] /* damper.v_rel STATE(1) */));
  threadData->lastEquationSolved = 34;
}

/*
equation index: 35
type: SIMPLE_ASSIGN
mass.v = -damper.v_rel
*/
void MassSpringDamperPlant_eqFunction_35(DATA *data, threadData_t *threadData)
{
  const int equationIndexes[2] = {1,35};
  (data->localData[0]->realVars[data->simulationInfo->realVarsIndex[26]] /* mass.v DUMMY_STATE */) = (-(data->localData[0]->realVars[data->simulationInfo->realVarsIndex[3]] /* damper.v_rel STATE(1) */));
  threadData->lastEquationSolved = 35;
}

/*
equation index: 36
type: SIMPLE_ASSIGN
$DER.positionSensor.s = -damper.v_rel
*/
void MassSpringDamperPlant_eqFunction_36(DATA *data, threadData_t *threadData)
{
  const int equationIndexes[2] = {1,36};
  (data->localData[0]->realVars[data->simulationInfo->realVarsIndex[11]] /* der(positionSensor.s) DUMMY_DER */) = (-(data->localData[0]->realVars[data->simulationInfo->realVarsIndex[3]] /* damper.v_rel STATE(1) */));
  threadData->lastEquationSolved = 36;
}

/*
equation index: 37
type: SIMPLE_ASSIGN
damper.f = damper.d * damper.v_rel
*/
void MassSpringDamperPlant_eqFunction_37(DATA *data, threadData_t *threadData)
{
  const int equationIndexes[2] = {1,37};
  (data->localData[0]->realVars[data->simulationInfo->realVarsIndex[16]] /* damper.f variable */) = ((data->simulationInfo->realParameter[data->simulationInfo->realParamsIndex[18]] /* damper.d PARAM */)) * ((data->localData[0]->realVars[data->simulationInfo->realVarsIndex[3]] /* damper.v_rel STATE(1) */));
  threadData->lastEquationSolved = 37;
}

/*
equation index: 38
type: SIMPLE_ASSIGN
damper.lossPower = damper.f * damper.v_rel
*/
void MassSpringDamperPlant_eqFunction_38(DATA *data, threadData_t *threadData)
{
  const int equationIndexes[2] = {1,38};
  (data->localData[0]->realVars[data->simulationInfo->realVarsIndex[17]] /* damper.lossPower variable */) = ((data->localData[0]->realVars[data->simulationInfo->realVarsIndex[16]] /* damper.f variable */)) * ((data->localData[0]->realVars[data->simulationInfo->realVarsIndex[3]] /* damper.v_rel STATE(1) */));
  threadData->lastEquationSolved = 38;
}

/*
equation index: 39
type: SIMPLE_ASSIGN
$DER.damper.s_rel = damper.v_rel
*/
void MassSpringDamperPlant_eqFunction_39(DATA *data, threadData_t *threadData)
{
  const int equationIndexes[2] = {1,39};
  (data->localData[0]->realVars[data->simulationInfo->realVarsIndex[6]] /* der(damper.s_rel) STATE_DER */) = (data->localData[0]->realVars[data->simulationInfo->realVarsIndex[3]] /* damper.v_rel STATE(1) */);
  threadData->lastEquationSolved = 39;
}

/*
equation index: 40
type: SIMPLE_ASSIGN
step.y = step.offset + (if time < step.startTime then 0.0 else step.height)
*/
void MassSpringDamperPlant_eqFunction_40(DATA *data, threadData_t *threadData)
{
  const int equationIndexes[2] = {1,40};
  modelica_boolean tmp0;
  modelica_real tmp1;
  modelica_real tmp2;
  tmp1 = 1.0;
  tmp2 = fabs((data->simulationInfo->realParameter[data->simulationInfo->realParamsIndex[27]] /* step.startTime PARAM */));
  relationhysteresis(data, &tmp0, data->localData[0]->timeValue, (data->simulationInfo->realParameter[data->simulationInfo->realParamsIndex[27]] /* step.startTime PARAM */), tmp1, tmp2, 0, Less, LessZC);
  (data->localData[0]->realVars[data->simulationInfo->realVarsIndex[31]] /* step.y variable */) = (data->simulationInfo->realParameter[data->simulationInfo->realParamsIndex[26]] /* step.offset PARAM */) + (tmp0?0.0:(data->simulationInfo->realParameter[data->simulationInfo->realParamsIndex[25]] /* step.height PARAM */));
  threadData->lastEquationSolved = 40;
}

/*
equation index: 41
type: SIMPLE_ASSIGN
positionSensor.s = fixed.s0 - damper.s_rel
*/
void MassSpringDamperPlant_eqFunction_41(DATA *data, threadData_t *threadData)
{
  const int equationIndexes[2] = {1,41};
  (data->localData[0]->realVars[data->simulationInfo->realVarsIndex[28]] /* positionSensor.s DUMMY_STATE */) = (data->simulationInfo->realParameter[data->simulationInfo->realParamsIndex[20]] /* fixed.s0 PARAM */) - (data->localData[0]->realVars[data->simulationInfo->realVarsIndex[2]] /* damper.s_rel STATE(1,damper.v_rel) */);
  threadData->lastEquationSolved = 41;
}

/*
equation index: 42
type: SIMPLE_ASSIGN
mass.s = positionSensor.s - 0.5 * mass.L
*/
void MassSpringDamperPlant_eqFunction_42(DATA *data, threadData_t *threadData)
{
  const int equationIndexes[2] = {1,42};
  (data->localData[0]->realVars[data->simulationInfo->realVarsIndex[25]] /* mass.s DUMMY_STATE */) = (data->localData[0]->realVars[data->simulationInfo->realVarsIndex[28]] /* positionSensor.s DUMMY_STATE */) - ((0.5) * ((data->simulationInfo->realParameter[data->simulationInfo->realParamsIndex[21]] /* mass.L PARAM */)));
  threadData->lastEquationSolved = 42;
}

/*
equation index: 43
type: SIMPLE_ASSIGN
force.s = mass.s + (-0.5) * mass.L
*/
void MassSpringDamperPlant_eqFunction_43(DATA *data, threadData_t *threadData)
{
  const int equationIndexes[2] = {1,43};
  (data->localData[0]->realVars[data->simulationInfo->realVarsIndex[21]] /* force.s variable */) = (data->localData[0]->realVars[data->simulationInfo->realVarsIndex[25]] /* mass.s DUMMY_STATE */) + (-0.5) * ((data->simulationInfo->realParameter[data->simulationInfo->realParamsIndex[21]] /* mass.L PARAM */));
  threadData->lastEquationSolved = 43;
}

/*
equation index: 44
type: SIMPLE_ASSIGN
feedback1.y = step.y - positionSensor.s
*/
void MassSpringDamperPlant_eqFunction_44(DATA *data, threadData_t *threadData)
{
  const int equationIndexes[2] = {1,44};
  (data->localData[0]->realVars[data->simulationInfo->realVarsIndex[18]] /* feedback1.y variable */) = (data->localData[0]->realVars[data->simulationInfo->realVarsIndex[31]] /* step.y variable */) - (data->localData[0]->realVars[data->simulationInfo->realVarsIndex[28]] /* positionSensor.s DUMMY_STATE */);
  threadData->lastEquationSolved = 44;
}

/*
equation index: 45
type: SIMPLE_ASSIGN
PID.P.y = PID.P.k * feedback1.y
*/
void MassSpringDamperPlant_eqFunction_45(DATA *data, threadData_t *threadData)
{
  const int equationIndexes[2] = {1,45};
  (data->localData[0]->realVars[data->simulationInfo->realVarsIndex[15]] /* PID.P.y variable */) = ((data->simulationInfo->realParameter[data->simulationInfo->realParamsIndex[11]] /* PID.P.k PARAM */)) * ((data->localData[0]->realVars[data->simulationInfo->realVarsIndex[18]] /* feedback1.y variable */));
  threadData->lastEquationSolved = 45;
}

/*
equation index: 46
type: SIMPLE_ASSIGN
$DER.PID.I.y = PID.I.k * feedback1.y
*/
void MassSpringDamperPlant_eqFunction_46(DATA *data, threadData_t *threadData)
{
  const int equationIndexes[2] = {1,46};
  (data->localData[0]->realVars[data->simulationInfo->realVarsIndex[5]] /* der(PID.I.y) STATE_DER */) = ((data->simulationInfo->realParameter[data->simulationInfo->realParamsIndex[8]] /* PID.I.k PARAM */)) * ((data->localData[0]->realVars[data->simulationInfo->realVarsIndex[18]] /* feedback1.y variable */));
  threadData->lastEquationSolved = 46;
}

/*
equation index: 47
type: SIMPLE_ASSIGN
$DER.PID.D.x = if PID.D.zeroGain then 0.0 else (feedback1.y - PID.D.x) / PID.D.T
*/
void MassSpringDamperPlant_eqFunction_47(DATA *data, threadData_t *threadData)
{
  const int equationIndexes[2] = {1,47};
  (data->localData[0]->realVars[data->simulationInfo->realVarsIndex[4]] /* der(PID.D.x) STATE_DER */) = ((data->simulationInfo->booleanParameter[data->simulationInfo->booleanParamsIndex[0]] /* PID.D.zeroGain PARAM */)?0.0:DIVISION_SIM((data->localData[0]->realVars[data->simulationInfo->realVarsIndex[18]] /* feedback1.y variable */) - (data->localData[0]->realVars[data->simulationInfo->realVarsIndex[0]] /* PID.D.x STATE(1) */),(data->simulationInfo->realParameter[data->simulationInfo->realParamsIndex[3]] /* PID.D.T PARAM */),"PID.D.T",equationIndexes));
  threadData->lastEquationSolved = 47;
}

/*
equation index: 48
type: SIMPLE_ASSIGN
PID.D.y = if PID.D.zeroGain then 0.0 else PID.D.k / PID.D.T * (feedback1.y - PID.D.x)
*/
void MassSpringDamperPlant_eqFunction_48(DATA *data, threadData_t *threadData)
{
  const int equationIndexes[2] = {1,48};
  (data->localData[0]->realVars[data->simulationInfo->realVarsIndex[13]] /* PID.D.y variable */) = ((data->simulationInfo->booleanParameter[data->simulationInfo->booleanParamsIndex[0]] /* PID.D.zeroGain PARAM */)?0.0:(DIVISION_SIM((data->simulationInfo->realParameter[data->simulationInfo->realParamsIndex[4]] /* PID.D.k PARAM */),(data->simulationInfo->realParameter[data->simulationInfo->realParamsIndex[3]] /* PID.D.T PARAM */),"PID.D.T",equationIndexes)) * ((data->localData[0]->realVars[data->simulationInfo->realVarsIndex[18]] /* feedback1.y variable */) - (data->localData[0]->realVars[data->simulationInfo->realVarsIndex[0]] /* PID.D.x STATE(1) */)));
  threadData->lastEquationSolved = 48;
}

/*
equation index: 49
type: SIMPLE_ASSIGN
PID.Add.y = PID.Add.k1 * PID.P.y + PID.Add.k2 * PID.I.y + PID.Add.k3 * PID.D.y
*/
void MassSpringDamperPlant_eqFunction_49(DATA *data, threadData_t *threadData)
{
  const int equationIndexes[2] = {1,49};
  (data->localData[0]->realVars[data->simulationInfo->realVarsIndex[12]] /* PID.Add.y variable */) = ((data->simulationInfo->realParameter[data->simulationInfo->realParamsIndex[0]] /* PID.Add.k1 PARAM */)) * ((data->localData[0]->realVars[data->simulationInfo->realVarsIndex[15]] /* PID.P.y variable */)) + ((data->simulationInfo->realParameter[data->simulationInfo->realParamsIndex[1]] /* PID.Add.k2 PARAM */)) * ((data->localData[0]->realVars[data->simulationInfo->realVarsIndex[1]] /* PID.I.y STATE(1) */)) + ((data->simulationInfo->realParameter[data->simulationInfo->realParamsIndex[2]] /* PID.Add.k3 PARAM */)) * ((data->localData[0]->realVars[data->simulationInfo->realVarsIndex[13]] /* PID.D.y variable */));
  threadData->lastEquationSolved = 49;
}

/*
equation index: 50
type: SIMPLE_ASSIGN
force.f = PID.Gain.k * PID.Add.y
*/
void MassSpringDamperPlant_eqFunction_50(DATA *data, threadData_t *threadData)
{
  const int equationIndexes[2] = {1,50};
  (data->localData[0]->realVars[data->simulationInfo->realVarsIndex[20]] /* force.f variable */) = ((data->simulationInfo->realParameter[data->simulationInfo->realParamsIndex[7]] /* PID.Gain.k PARAM */)) * ((data->localData[0]->realVars[data->simulationInfo->realVarsIndex[12]] /* PID.Add.y variable */));
  threadData->lastEquationSolved = 50;
}

/*
equation index: 51
type: SIMPLE_ASSIGN
spring.s_rel = fixed.s0 - positionSensor.s
*/
void MassSpringDamperPlant_eqFunction_51(DATA *data, threadData_t *threadData)
{
  const int equationIndexes[2] = {1,51};
  (data->localData[0]->realVars[data->simulationInfo->realVarsIndex[30]] /* spring.s_rel variable */) = (data->simulationInfo->realParameter[data->simulationInfo->realParamsIndex[20]] /* fixed.s0 PARAM */) - (data->localData[0]->realVars[data->simulationInfo->realVarsIndex[28]] /* positionSensor.s DUMMY_STATE */);
  threadData->lastEquationSolved = 51;
}

/*
equation index: 52
type: SIMPLE_ASSIGN
spring.f = spring.c * (spring.s_rel - spring.s_rel0)
*/
void MassSpringDamperPlant_eqFunction_52(DATA *data, threadData_t *threadData)
{
  const int equationIndexes[2] = {1,52};
  (data->localData[0]->realVars[data->simulationInfo->realVarsIndex[29]] /* spring.f variable */) = ((data->simulationInfo->realParameter[data->simulationInfo->realParamsIndex[23]] /* spring.c PARAM */)) * ((data->localData[0]->realVars[data->simulationInfo->realVarsIndex[30]] /* spring.s_rel variable */) - (data->simulationInfo->realParameter[data->simulationInfo->realParamsIndex[24]] /* spring.s_rel0 PARAM */));
  threadData->lastEquationSolved = 52;
}

/*
equation index: 53
type: SIMPLE_ASSIGN
mass.flange_b.f = spring.f + damper.f
*/
void MassSpringDamperPlant_eqFunction_53(DATA *data, threadData_t *threadData)
{
  const int equationIndexes[2] = {1,53};
  (data->localData[0]->realVars[data->simulationInfo->realVarsIndex[24]] /* mass.flange_b.f variable */) = (data->localData[0]->realVars[data->simulationInfo->realVarsIndex[29]] /* spring.f variable */) + (data->localData[0]->realVars[data->simulationInfo->realVarsIndex[16]] /* damper.f variable */);
  threadData->lastEquationSolved = 53;
}

/*
equation index: 54
type: SIMPLE_ASSIGN
mass.a = (force.f + mass.flange_b.f) / mass.m
*/
void MassSpringDamperPlant_eqFunction_54(DATA *data, threadData_t *threadData)
{
  const int equationIndexes[2] = {1,54};
  (data->localData[0]->realVars[data->simulationInfo->realVarsIndex[23]] /* mass.a variable */) = DIVISION_SIM((data->localData[0]->realVars[data->simulationInfo->realVarsIndex[20]] /* force.f variable */) + (data->localData[0]->realVars[data->simulationInfo->realVarsIndex[24]] /* mass.flange_b.f variable */),(data->simulationInfo->realParameter[data->simulationInfo->realParamsIndex[22]] /* mass.m PARAM */),"mass.m",equationIndexes);
  threadData->lastEquationSolved = 54;
}

/*
equation index: 55
type: SIMPLE_ASSIGN
$DER.damper.v_rel = -mass.a
*/
void MassSpringDamperPlant_eqFunction_55(DATA *data, threadData_t *threadData)
{
  const int equationIndexes[2] = {1,55};
  (data->localData[0]->realVars[data->simulationInfo->realVarsIndex[7]] /* der(damper.v_rel) STATE_DER */) = (-(data->localData[0]->realVars[data->simulationInfo->realVarsIndex[23]] /* mass.a variable */));
  threadData->lastEquationSolved = 55;
}

/*
equation index: 56
type: SIMPLE_ASSIGN
$DER.mass.v = mass.a
*/
void MassSpringDamperPlant_eqFunction_56(DATA *data, threadData_t *threadData)
{
  const int equationIndexes[2] = {1,56};
  (data->localData[0]->realVars[data->simulationInfo->realVarsIndex[10]] /* der(mass.v) DUMMY_DER */) = (data->localData[0]->realVars[data->simulationInfo->realVarsIndex[23]] /* mass.a variable */);
  threadData->lastEquationSolved = 56;
}

/*
equation index: 57
type: SIMPLE_ASSIGN
$DER.$DER.positionSensor.s = mass.a
*/
void MassSpringDamperPlant_eqFunction_57(DATA *data, threadData_t *threadData)
{
  const int equationIndexes[2] = {1,57};
  (data->localData[0]->realVars[data->simulationInfo->realVarsIndex[8]] /* der(der(positionSensor.s)) DUMMY_DER */) = (data->localData[0]->realVars[data->simulationInfo->realVarsIndex[23]] /* mass.a variable */);
  threadData->lastEquationSolved = 57;
}

/*
equation index: 58
type: SIMPLE_ASSIGN
fixed.flange.f = -mass.flange_b.f
*/
void MassSpringDamperPlant_eqFunction_58(DATA *data, threadData_t *threadData)
{
  const int equationIndexes[2] = {1,58};
  (data->localData[0]->realVars[data->simulationInfo->realVarsIndex[19]] /* fixed.flange.f variable */) = (-(data->localData[0]->realVars[data->simulationInfo->realVarsIndex[24]] /* mass.flange_b.f variable */));
  threadData->lastEquationSolved = 58;
}

OMC_DISABLE_OPT
int MassSpringDamperPlant_functionDAE(DATA *data, threadData_t *threadData)
{
  int equationIndexes[1] = {0};
#if !defined(OMC_MINIMAL_RUNTIME)
  if (measure_time_flag) rt_tick(SIM_TIMER_DAE);
#endif

  data->simulationInfo->needToIterate = 0;
  data->simulationInfo->discreteCall = 1;
  MassSpringDamperPlant_functionLocalKnownVars(data, threadData);
  static void (*const eqFunctions[25])(DATA*, threadData_t*) = {
    MassSpringDamperPlant_eqFunction_34,
    MassSpringDamperPlant_eqFunction_35,
    MassSpringDamperPlant_eqFunction_36,
    MassSpringDamperPlant_eqFunction_37,
    MassSpringDamperPlant_eqFunction_38,
    MassSpringDamperPlant_eqFunction_39,
    MassSpringDamperPlant_eqFunction_40,
    MassSpringDamperPlant_eqFunction_41,
    MassSpringDamperPlant_eqFunction_42,
    MassSpringDamperPlant_eqFunction_43,
    MassSpringDamperPlant_eqFunction_44,
    MassSpringDamperPlant_eqFunction_45,
    MassSpringDamperPlant_eqFunction_46,
    MassSpringDamperPlant_eqFunction_47,
    MassSpringDamperPlant_eqFunction_48,
    MassSpringDamperPlant_eqFunction_49,
    MassSpringDamperPlant_eqFunction_50,
    MassSpringDamperPlant_eqFunction_51,
    MassSpringDamperPlant_eqFunction_52,
    MassSpringDamperPlant_eqFunction_53,
    MassSpringDamperPlant_eqFunction_54,
    MassSpringDamperPlant_eqFunction_55,
    MassSpringDamperPlant_eqFunction_56,
    MassSpringDamperPlant_eqFunction_57,
    MassSpringDamperPlant_eqFunction_58
  };
  
  for (int id = 0; id < 25; id++) {
    eqFunctions[id](data, threadData);
  }
  data->simulationInfo->discreteCall = 0;
  
#if !defined(OMC_MINIMAL_RUNTIME)
  if (measure_time_flag) rt_accumulate(SIM_TIMER_DAE);
#endif
  return 0;
}


int MassSpringDamperPlant_functionLocalKnownVars(DATA *data, threadData_t *threadData)
{
  
  return 0;
}

/* forwarded equations */
extern void MassSpringDamperPlant_eqFunction_37(DATA* data, threadData_t *threadData);
extern void MassSpringDamperPlant_eqFunction_39(DATA* data, threadData_t *threadData);
extern void MassSpringDamperPlant_eqFunction_40(DATA* data, threadData_t *threadData);
extern void MassSpringDamperPlant_eqFunction_41(DATA* data, threadData_t *threadData);
extern void MassSpringDamperPlant_eqFunction_44(DATA* data, threadData_t *threadData);
extern void MassSpringDamperPlant_eqFunction_45(DATA* data, threadData_t *threadData);
extern void MassSpringDamperPlant_eqFunction_46(DATA* data, threadData_t *threadData);
extern void MassSpringDamperPlant_eqFunction_47(DATA* data, threadData_t *threadData);
extern void MassSpringDamperPlant_eqFunction_48(DATA* data, threadData_t *threadData);
extern void MassSpringDamperPlant_eqFunction_49(DATA* data, threadData_t *threadData);
extern void MassSpringDamperPlant_eqFunction_50(DATA* data, threadData_t *threadData);
extern void MassSpringDamperPlant_eqFunction_51(DATA* data, threadData_t *threadData);
extern void MassSpringDamperPlant_eqFunction_52(DATA* data, threadData_t *threadData);
extern void MassSpringDamperPlant_eqFunction_53(DATA* data, threadData_t *threadData);
extern void MassSpringDamperPlant_eqFunction_54(DATA* data, threadData_t *threadData);
extern void MassSpringDamperPlant_eqFunction_55(DATA* data, threadData_t *threadData);

static void functionODE_system0(DATA *data, threadData_t *threadData)
{
  static void (*const eqFunctions[16])(DATA*, threadData_t*) = {
    MassSpringDamperPlant_eqFunction_37,
    MassSpringDamperPlant_eqFunction_39,
    MassSpringDamperPlant_eqFunction_40,
    MassSpringDamperPlant_eqFunction_41,
    MassSpringDamperPlant_eqFunction_44,
    MassSpringDamperPlant_eqFunction_45,
    MassSpringDamperPlant_eqFunction_46,
    MassSpringDamperPlant_eqFunction_47,
    MassSpringDamperPlant_eqFunction_48,
    MassSpringDamperPlant_eqFunction_49,
    MassSpringDamperPlant_eqFunction_50,
    MassSpringDamperPlant_eqFunction_51,
    MassSpringDamperPlant_eqFunction_52,
    MassSpringDamperPlant_eqFunction_53,
    MassSpringDamperPlant_eqFunction_54,
    MassSpringDamperPlant_eqFunction_55
  };
  
  if (data->simulationInfo->evalSelection) {
    for (int i = 0; i < data->simulationInfo->evalSelection->n; i++) {
      int id = data->simulationInfo->evalSelection->idx[i];
      eqFunctions[id](data, threadData);
    }
  } else {
    for (int id = 0; id < 16; id++) {
      eqFunctions[id](data, threadData);
    }
  }
}

int MassSpringDamperPlant_functionODE(DATA *data, threadData_t *threadData)
{
#if !defined(OMC_MINIMAL_RUNTIME)
  if (measure_time_flag) rt_tick(SIM_TIMER_FUNCTION_ODE);
#endif

  
  data->simulationInfo->callStatistics.functionODE++;
  
  MassSpringDamperPlant_functionLocalKnownVars(data, threadData);
  functionODE_system0(data, threadData);

#if !defined(OMC_MINIMAL_RUNTIME)
  if (measure_time_flag) rt_accumulate(SIM_TIMER_FUNCTION_ODE);
#endif

  return 0;
}

void MassSpringDamperPlant_ODE_DAG(DATA* data, threadData_t* threadData)
{
  const size_t eqMap[] = {37, 39, 40, 41, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55};
  buildEvalDAG_ODE(data->modelData, sizeof(eqMap)/sizeof(size_t), eqMap);
}

/* forward the main in the simulation runtime */
extern int _main_SimulationRuntime(int argc, char **argv, DATA *data, threadData_t *threadData);
extern int _main_OptimizationRuntime(int argc, char **argv, DATA *data, threadData_t *threadData);

#include "MassSpringDamperPlant_12jac.h"
#include "MassSpringDamperPlant_13opt.h"

struct OpenModelicaGeneratedFunctionCallbacks MassSpringDamperPlant_callback = {
  (int (*)(DATA *, threadData_t *, void *)) MassSpringDamperPlant_performSimulation,    /* performSimulation */
  (int (*)(DATA *, threadData_t *, void *)) MassSpringDamperPlant_performQSSSimulation,    /* performQSSSimulation */
  MassSpringDamperPlant_updateContinuousSystem,    /* updateContinuousSystem */
  MassSpringDamperPlant_callExternalObjectDestructors,    /* callExternalObjectDestructors */
  NULL,    /* initialNonLinearSystem */
  NULL,    /* initialLinearSystem */
  NULL,    /* initialMixedSystem */
  #if !defined(OMC_NO_STATESELECTION)
  MassSpringDamperPlant_initializeStateSets,
  #else
  NULL,
  #endif    /* initializeStateSets */
  MassSpringDamperPlant_initializeDAEmodeData,
  MassSpringDamperPlant_ODE_DAG,
  MassSpringDamperPlant_functionODE,
  MassSpringDamperPlant_functionAlgebraics,
  MassSpringDamperPlant_functionDAE,
  MassSpringDamperPlant_functionLocalKnownVars,
  MassSpringDamperPlant_input_function,
  MassSpringDamperPlant_input_function_init,
  MassSpringDamperPlant_input_function_updateStartValues,
  MassSpringDamperPlant_data_function,
  MassSpringDamperPlant_output_function,
  MassSpringDamperPlant_setc_function,
  MassSpringDamperPlant_setb_function,
  MassSpringDamperPlant_function_storeDelayed,
  MassSpringDamperPlant_function_storeSpatialDistribution,
  MassSpringDamperPlant_function_initSpatialDistribution,
  MassSpringDamperPlant_updateBoundVariableAttributes,
  MassSpringDamperPlant_functionInitialEquations,
  GLOBAL_EQUIDISTANT_HOMOTOPY,
  NULL,
  MassSpringDamperPlant_functionRemovedInitialEquations,
  MassSpringDamperPlant_updateBoundParameters,
  MassSpringDamperPlant_checkForAsserts,
  MassSpringDamperPlant_function_ZeroCrossingsEquations,
  MassSpringDamperPlant_function_ZeroCrossings,
  MassSpringDamperPlant_function_updateRelations,
  MassSpringDamperPlant_zeroCrossingDescription,
  MassSpringDamperPlant_relationDescription,
  MassSpringDamperPlant_function_initSample,
  MassSpringDamperPlant_INDEX_JAC_A,
  MassSpringDamperPlant_INDEX_JAC_ADJ,
  MassSpringDamperPlant_INDEX_JAC_B,
  MassSpringDamperPlant_INDEX_JAC_C,
  MassSpringDamperPlant_INDEX_JAC_D,
  MassSpringDamperPlant_INDEX_JAC_F,
  MassSpringDamperPlant_INDEX_JAC_H,
  MassSpringDamperPlant_initialAnalyticJacobianA,
  MassSpringDamperPlant_initialAnalyticJacobianADJ,
  MassSpringDamperPlant_initialAnalyticJacobianB,
  MassSpringDamperPlant_initialAnalyticJacobianC,
  MassSpringDamperPlant_initialAnalyticJacobianD,
  MassSpringDamperPlant_initialAnalyticJacobianF,
  MassSpringDamperPlant_initialAnalyticJacobianH,
  MassSpringDamperPlant_functionJacA_column,
  MassSpringDamperPlant_functionJacADJ_column,
  MassSpringDamperPlant_functionJacB_column,
  MassSpringDamperPlant_functionJacC_column,
  MassSpringDamperPlant_functionJacD_column,
  MassSpringDamperPlant_functionJacF_column,
  MassSpringDamperPlant_functionJacH_column,
  MassSpringDamperPlant_JacA_DAG,
  MassSpringDamperPlant_linear_model_frame,
  MassSpringDamperPlant_linear_model_datarecovery_frame,
  MassSpringDamperPlant_mayer,
  MassSpringDamperPlant_lagrange,
  MassSpringDamperPlant_getInputVarIndicesInOptimization,
  MassSpringDamperPlant_pickUpBoundsForInputsInOptimization,
  MassSpringDamperPlant_setInputData,
  MassSpringDamperPlant_getTimeGrid,
  MassSpringDamperPlant_symbolicInlineSystem,
  MassSpringDamperPlant_function_initSynchronous,
  MassSpringDamperPlant_function_updateSynchronous,
  MassSpringDamperPlant_function_equationsSynchronous,
  MassSpringDamperPlant_inputNames,
  MassSpringDamperPlant_dataReconciliationInputNames,
  MassSpringDamperPlant_dataReconciliationUnmeasuredVariables,
  NULL,
  NULL,
  NULL,
  NULL,
  -1,
  NULL,
  NULL,
  -1

};

#define _OMC_LIT_RESOURCE_0_name_data "Complex"
#define _OMC_LIT_RESOURCE_0_dir_data "/home/th3blaacksh33p/.openmodelica/libraries/Complex 4.1.0+maint.om"
static const MMC_DEFSTRINGLIT(_OMC_LIT_RESOURCE_0_name,7,_OMC_LIT_RESOURCE_0_name_data);
static const MMC_DEFSTRINGLIT(_OMC_LIT_RESOURCE_0_dir,67,_OMC_LIT_RESOURCE_0_dir_data);

#define _OMC_LIT_RESOURCE_1_name_data "MassSpringDamperPlant"
#define _OMC_LIT_RESOURCE_1_dir_data "/home/th3blaacksh33p/Documents/PyCircuits/OpenModelicaFiles"
static const MMC_DEFSTRINGLIT(_OMC_LIT_RESOURCE_1_name,21,_OMC_LIT_RESOURCE_1_name_data);
static const MMC_DEFSTRINGLIT(_OMC_LIT_RESOURCE_1_dir,59,_OMC_LIT_RESOURCE_1_dir_data);

#define _OMC_LIT_RESOURCE_2_name_data "Modelica"
#define _OMC_LIT_RESOURCE_2_dir_data "/home/th3blaacksh33p/.openmodelica/libraries/Modelica 4.1.0+maint.om"
static const MMC_DEFSTRINGLIT(_OMC_LIT_RESOURCE_2_name,8,_OMC_LIT_RESOURCE_2_name_data);
static const MMC_DEFSTRINGLIT(_OMC_LIT_RESOURCE_2_dir,68,_OMC_LIT_RESOURCE_2_dir_data);

#define _OMC_LIT_RESOURCE_3_name_data "ModelicaServices"
#define _OMC_LIT_RESOURCE_3_dir_data "/home/th3blaacksh33p/.openmodelica/libraries/ModelicaServices 4.1.0+maint.om"
static const MMC_DEFSTRINGLIT(_OMC_LIT_RESOURCE_3_name,16,_OMC_LIT_RESOURCE_3_name_data);
static const MMC_DEFSTRINGLIT(_OMC_LIT_RESOURCE_3_dir,76,_OMC_LIT_RESOURCE_3_dir_data);

static const MMC_DEFSTRUCTLIT(_OMC_LIT_RESOURCES,8,MMC_ARRAY_TAG) {MMC_REFSTRINGLIT(_OMC_LIT_RESOURCE_0_name), MMC_REFSTRINGLIT(_OMC_LIT_RESOURCE_0_dir), MMC_REFSTRINGLIT(_OMC_LIT_RESOURCE_1_name), MMC_REFSTRINGLIT(_OMC_LIT_RESOURCE_1_dir), MMC_REFSTRINGLIT(_OMC_LIT_RESOURCE_2_name), MMC_REFSTRINGLIT(_OMC_LIT_RESOURCE_2_dir), MMC_REFSTRINGLIT(_OMC_LIT_RESOURCE_3_name), MMC_REFSTRINGLIT(_OMC_LIT_RESOURCE_3_dir)}};
void MassSpringDamperPlant_setupDataStruc(DATA *data, threadData_t *threadData)
{
  assertStreamPrint(threadData,0!=data, "Error while initialize Data");
  threadData->localRoots[LOCAL_ROOT_SIMULATION_DATA] = data;
  data->callback = &MassSpringDamperPlant_callback;
  OpenModelica_updateUriMapping(threadData, MMC_REFSTRUCTLIT(_OMC_LIT_RESOURCES));
  data->modelData->modelName = "MassSpringDamperPlant";
  data->modelData->modelFilePrefix = "MassSpringDamperPlant";
  data->modelData->modelFileName = "MassSpringDamperPlant.mo";
  data->modelData->resultFileName = NULL;
  data->modelData->modelDir = "/home/th3blaacksh33p/Documents/PyCircuits/OpenModelicaFiles";
  data->modelData->modelGUID = "{d6fa394c-2051-4062-a694-9808169b8d21}";
  #if defined(OPENMODELICA_XML_FROM_FILE_AT_RUNTIME)
  data->modelData->initXMLData = NULL;
  data->modelData->modelDataXml.infoXMLData = NULL;
  #else
  #if defined(_MSC_VER) /* handle joke compilers */
  {
  /* for MSVC we encode a string like char x[] = {'a', 'b', 'c', '\0'} */
  /* because the string constant limit is 65535 bytes */
  static const char contents_init[] =
    #include "MassSpringDamperPlant_init.c"
    ;
  static const char contents_info[] =
    #include "MassSpringDamperPlant_info.c"
    ;
    data->modelData->initXMLData = contents_init;
    data->modelData->modelDataXml.infoXMLData = contents_info;
  }
  #else /* handle real compilers */
  data->modelData->initXMLData =
  #include "MassSpringDamperPlant_init.c"
    ;
  data->modelData->modelDataXml.infoXMLData =
  #include "MassSpringDamperPlant_info.c"
    ;
  #endif /* defined(_MSC_VER) */
  #endif /* defined(OPENMODELICA_XML_FROM_FILE_AT_RUNTIME) */
  data->modelData->modelDataXml.fileName = "MassSpringDamperPlant_info.json";
  data->modelData->resourcesDir = NULL;
  data->modelData->runTestsuite = 0;
  data->modelData->nStatesArray = 4;
  data->modelData->nDiscreteReal = 0;
  data->modelData->nVariablesRealArray = 32;
  data->modelData->nVariablesIntegerArray = 0;
  data->modelData->nVariablesBooleanArray = 1;
  data->modelData->nVariablesStringArray = 0;
  data->modelData->nParametersRealArray = 28;
  data->modelData->nParametersIntegerArray = 5;
  data->modelData->nParametersBooleanArray = 5;
  data->modelData->nParametersStringArray = 0;
  data->modelData->nParametersReal = 28;
  data->modelData->nParametersInteger = 5;
  data->modelData->nParametersBoolean = 5;
  data->modelData->nParametersString = 0;
  data->modelData->nAliasRealArray = 27;
  data->modelData->nAliasIntegerArray = 0;
  data->modelData->nAliasBooleanArray = 0;
  data->modelData->nAliasStringArray = 0;
  data->modelData->nInputVars = 0;
  data->modelData->nOutputVars = 0;
  data->modelData->nZeroCrossings = 1;
  data->modelData->nSamples = 0;
  data->modelData->nRelations = 1;
  data->modelData->nMathEvents = 0;
  data->modelData->nExtObjs = 0;
  data->modelData->modelDataXml.modelInfoXmlLength = 0;
  data->modelData->modelDataXml.nFunctions = 0;
  data->modelData->modelDataXml.nProfileBlocks = 0;
  data->modelData->modelDataXml.nEquations = 95;
  data->modelData->nMixedSystems = 0;
  data->modelData->nLinearSystems = 0;
  data->modelData->nNonLinearSystems = 0;
  data->modelData->nStateSets = 0;
  data->modelData->nJacobians = 7;
  data->modelData->nOptimizeConstraints = 0;
  data->modelData->nOptimizeFinalConstraints = 0;
  data->modelData->nDelayExpressions = 0;
  data->modelData->nBaseClocks = 0;
  data->modelData->nSpatialDistributions = 0;
  data->modelData->nSensitivityVars = 0;
  data->modelData->nSensitivityParamVars = 0;
  data->modelData->nSetcVars = 0;
  data->modelData->ndataReconVars = 0;
  data->modelData->nSetbVars = 0;
  data->modelData->nRelatedBoundaryConditions = 0;
  data->modelData->linearizationDumpLanguage = OMC_LINEARIZE_DUMP_LANGUAGE_MODELICA;
}

static int rml_execution_failed()
{
  fflush(NULL);
  fprintf(stderr, "Execution failed!\n");
  fflush(NULL);
  return 1;
}


#if defined(__MINGW32__) || defined(_MSC_VER)

#if !defined(_UNICODE)
#define _UNICODE
#endif
#if !defined(UNICODE)
#define UNICODE
#endif

#include <windows.h>
char** omc_fixWindowsArgv(int argc, wchar_t **wargv)
{
  char** newargv;
  /* Support for non-ASCII characters
  * Read the unicode command line arguments and translate it to char*
  */
  newargv = (char**)malloc(argc*sizeof(char*));
  for (int i = 0; i < argc; i++) {
    newargv[i] = omc_wchar_to_multibyte_str(wargv[i]);
  }
  return newargv;
}

#define OMC_MAIN wmain
#define OMC_CHAR wchar_t
#define OMC_EXPORT __declspec(dllexport) extern

#else
#define omc_fixWindowsArgv(N, A) (A)
#define OMC_MAIN main
#define OMC_CHAR char
#define OMC_EXPORT extern
#endif

#if defined(threadData)
#undef threadData
#endif
/* call the simulation runtime main from our main! */
#if defined(OMC_DLL_MAIN_DEFINE)
OMC_EXPORT int omcDllMain(int argc, OMC_CHAR **argv)
#else
int OMC_MAIN(int argc, OMC_CHAR** argv)
#endif
{
  char** newargv = omc_fixWindowsArgv(argc, argv);
  /*
    Set the error functions to be used for simulation.
    The default value for them is 'functions' version. Change it here to 'simulation' versions
  */
  omc_assert = omc_assert_simulation;
  omc_assert_withEquationIndexes = omc_assert_simulation_withEquationIndexes;

  omc_assert_warning_withEquationIndexes = omc_assert_warning_simulation_withEquationIndexes;
  omc_assert_warning = omc_assert_warning_simulation;
  omc_terminate = omc_terminate_simulation;
  omc_throw = omc_throw_simulation;

  int res;
  DATA data;
  MODEL_DATA modelData;
  SIMULATION_INFO simInfo;
  data.modelData = &modelData;
  data.simulationInfo = &simInfo;
  measure_time_flag = 0;
  compiledInDAEMode = 0;
  compiledWithSymSolver = 0;
  MMC_INIT(0);
  omc_alloc_interface.init();
  {
    MMC_TRY_TOP()
  
    MMC_TRY_STACK()
  
    MassSpringDamperPlant_setupDataStruc(&data, threadData);
    res = _main_initRuntimeAndSimulation(argc, newargv, &data, threadData);
    if(res == 0) {
      if (omc_flag[FLAG_MOO_OPTIMIZATION]) {
        res = _main_OptimizationRuntime(argc, newargv, &data, threadData);
      } else {
        res = _main_SimulationRuntime(argc, newargv, &data, threadData);
      }
    }
    
    MMC_ELSE()
    rml_execution_failed();
    fprintf(stderr, "Stack overflow detected and was not caught.\nSend us a bug report at https://trac.openmodelica.org/OpenModelica/newticket\n    Include the following trace:\n");
    printStacktraceMessages();
    fflush(NULL);
    return 1;
    MMC_CATCH_STACK()
    
    MMC_CATCH_TOP(return rml_execution_failed());
  }

  fflush(NULL);
  return res;
}

#ifdef __cplusplus
}
#endif


