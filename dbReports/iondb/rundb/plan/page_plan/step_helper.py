# Copyright (C) 2013 Ion Torrent Systems, Inc. All Rights Reserved
'''
Created on May 21, 2013

@author: ionadmin
'''
import logging

from iondb.rundb.plan.page_plan.application_step_data import ApplicationStepData
from iondb.rundb.plan.page_plan.kits_step_data import KitsStepData,KitsFieldNames
from iondb.rundb.plan.page_plan.monitoring_step_data import MonitoringStepData
from iondb.rundb.plan.page_plan.reference_step_data import ReferenceStepData
from iondb.rundb.plan.page_plan.plugins_step_data import PluginsStepData
from iondb.rundb.plan.page_plan.output_step_data import OutputStepData
from iondb.rundb.plan.page_plan.ionreporter_step_data import IonreporterStepData
from iondb.rundb.plan.page_plan.save_template_step_data import SaveTemplateStepData
from iondb.rundb.plan.page_plan.save_plan_step_data import SavePlanStepData, SavePlanFieldNames
from iondb.rundb.plan.page_plan.barcode_by_sample_step_data import BarcodeBySampleStepData
#from iondb.rundb.plan.page_plan.output_by_sample_step_data import OutputBySampleStepData
from iondb.rundb.plan.page_plan.save_plan_by_sample_step_data import SavePlanBySampleStepData
from iondb.rundb.plan.page_plan.save_template_by_sample_step_data import SaveTemplateBySampleStepData
from iondb.rundb.plan.page_plan.step_names import StepNames

from iondb.rundb.plan.page_plan.application_step_data import ApplicationFieldNames

from iondb.rundb.plan.page_plan.step_helper_types import StepHelperType

from iondb.rundb.models import ApplicationGroup

from iondb.rundb.plan.views_helper import isOCP_enabled

try:
    from collections import OrderedDict
except ImportError:
    from ordereddict import OrderedDict

from iondb.rundb.models import KitInfo, Chip
    
logger = logging.getLogger(__name__)


class StepHelper(object):
    '''
    Helper class for interacting with the plan/template creation steps.
    '''

    def __init__(self, sh_type=StepHelperType.CREATE_NEW_TEMPLATE, previous_template_id=-1, previous_plan_id=-1):
        self.sh_type = sh_type
        self.previous_template_id = previous_template_id
        self.previous_plan_id = previous_plan_id
        self.parentName = None
        
        if (sh_type in [StepHelperType.EDIT_PLAN, StepHelperType.EDIT_PLAN_BY_SAMPLE, StepHelperType.EDIT_RUN, StepHelperType.EDIT_TEMPLATE] and previous_template_id == -1 and previous_plan_id == -1):
            logger.error("step_helper - StepHelper.init() for EDIT should have an existing ID.")
            raise ValueError("You must pass in a plan id or a template id.")
        
        self.steps = OrderedDict()
        if sh_type == StepHelperType.CREATE_NEW_PLAN_BY_SAMPLE or sh_type == StepHelperType.EDIT_PLAN_BY_SAMPLE or sh_type == StepHelperType.COPY_PLAN_BY_SAMPLE:
            referenceStepData = ReferenceStepData(sh_type)
            barcodeBySampleStepData = BarcodeBySampleStepData(sh_type)
            
            steps_list = [IonreporterStepData(sh_type), ApplicationStepData(sh_type), KitsStepData(sh_type),
                      referenceStepData, PluginsStepData(sh_type), barcodeBySampleStepData, 
                      OutputStepData(sh_type), SavePlanBySampleStepData(sh_type)]
            
            #some section can appear in multiple chevrons, key is the step name and value is the step_data object
            barcodeBySampleStepData.step_sections.update({StepNames.REFERENCE : referenceStepData})
            
        elif sh_type == StepHelperType.CREATE_NEW_TEMPLATE_BY_SAMPLE:            
            referenceStepData = ReferenceStepData(sh_type)
            saveTemplateBySampleData = SaveTemplateBySampleStepData(sh_type)
            
            steps_list = [IonreporterStepData(sh_type), ApplicationStepData(sh_type), KitsStepData(sh_type),
                      referenceStepData, PluginsStepData(sh_type), 
                      OutputStepData(sh_type), saveTemplateBySampleData]     
            
            saveTemplateBySampleData.step_sections.update({StepNames.REFERENCE : referenceStepData})            

        elif sh_type == StepHelperType.COPY_TEMPLATE or sh_type == StepHelperType.CREATE_NEW_TEMPLATE or sh_type == StepHelperType.EDIT_TEMPLATE:            
            referenceStepData = ReferenceStepData(sh_type)
            saveTemplateStepData = SaveTemplateStepData(sh_type)
            
            steps_list = [IonreporterStepData(sh_type), ApplicationStepData(sh_type), KitsStepData(sh_type),
                      referenceStepData, PluginsStepData(sh_type), OutputStepData(sh_type),
                      saveTemplateStepData]  
              
            saveTemplateStepData.step_sections.update({StepNames.REFERENCE : referenceStepData})
        else:

            referenceStepData = ReferenceStepData(sh_type)
            #SaveTemplateStepData is needed for the last chevron during plan creation 
            saveTemplateStepData = SaveTemplateStepData(sh_type)
            savePlanStepData = SavePlanStepData(sh_type)

            steps_list = [IonreporterStepData(sh_type), ApplicationStepData(sh_type), KitsStepData(sh_type),
                      referenceStepData, PluginsStepData(sh_type), OutputStepData(sh_type),
                      saveTemplateStepData, savePlanStepData]  

            savePlanStepData.step_sections.update({StepNames.REFERENCE : referenceStepData})            ###referenceStepData.sectionParentStep = savePlanStepData
            
        for step in steps_list:
            self.steps[step.getStepName()] = step

        self.update_dependent_steps(self.steps[StepNames.APPLICATION])

    
    def getStepDict(self):
        return self.steps
    
    def updateStepFromRequest(self, request, step_name):
        logger.debug("updateStepFromRequest... Updating %s with data from %s" % (step_name, str(request.POST)))
        if step_name in self.getStepDict():
            step = self.steps[step_name]
            retval = step.updateSavedFieldValuesFromRequest(request)
            if retval:
                step.updateSavedObjectsFromSavedFields()
                self.update_dependent_steps(step)
            return retval
        return False
    
    def update_dependent_steps(self, updated_step):
        '''
            Applies updates to all steps that depend on the updated step.
            If other steps depend on a step that got updated does that too.
        '''
        updated_steps = [updated_step]
        
        while updated_steps:
            updated_step = updated_steps[0]
            for dependent_step in self.steps.values():
                
                # if editing run post-sequencing, don't load defaults when application changes
                if self.isEditRun() and updated_step.getStepName() == StepNames.APPLICATION:
                    if updated_step.getStepName() in dependent_step._dependsOn:
                        dependent_step.alternateUpdateFromStep(updated_step)
                        updated_steps.append(dependent_step)
                        continue
                 
                if updated_step.getStepName() in dependent_step._dependsOn:
                    dependent_step.updateFromStep(updated_step)
                    updated_steps.append(dependent_step)
                
                # need to update barcode Set here to avoid circular dependency
                if updated_step.getStepName() == StepNames.SAVE_PLAN:
                    self.steps[StepNames.KITS].savedFields[KitsFieldNames.BARCODE_ID] = updated_step.savedFields[SavePlanFieldNames.BARCODE_SET]
                    
            updated_steps.remove(updated_step)
    
    def isPlan(self):
        return self.sh_type in StepHelperType.PLAN_TYPES

    def isPlanBySample(self):
        return self.sh_type in (StepHelperType.CREATE_NEW_PLAN_BY_SAMPLE, StepHelperType.EDIT_PLAN_BY_SAMPLE, StepHelperType.COPY_PLAN_BY_SAMPLE)
    
    def isTemplate(self):
        return self.sh_type in StepHelperType.TEMPLATE_TYPES

    def isTemplateBySample(self):
        return self.sh_type == StepHelperType.CREATE_NEW_TEMPLATE_BY_SAMPLE
    
    def isBarcoded(self):

        if self.steps[StepNames.KITS].savedFields[KitsFieldNames.BARCODE_ID]:
            return True
        return False
    
    def isCreate(self):
        return self.sh_type in [StepHelperType.CREATE_NEW_PLAN, StepHelperType.CREATE_NEW_TEMPLATE, StepHelperType.CREATE_NEW_PLAN_BY_SAMPLE]
    
    def isEdit(self):
        return self.sh_type in [StepHelperType.EDIT_PLAN, StepHelperType.EDIT_TEMPLATE, StepHelperType.EDIT_PLAN_BY_SAMPLE]
    
    def isEditRun(self):
        return self.sh_type in [StepHelperType.EDIT_RUN]
    
    def isCopy(self):
        return self.sh_type in [StepHelperType.COPY_PLAN, StepHelperType.COPY_TEMPLATE, StepHelperType.COPY_PLAN_BY_SAMPLE]
    
    def isIonChef(self):
        selectedTemplateKit = self.steps[StepNames.KITS].savedFields[KitsFieldNames.TEMPLATE_KIT_NAME]
        isIonChef = False
        
        if (selectedTemplateKit):
            kits = KitInfo.objects.filter(name = selectedTemplateKit)
            if kits:
                isIonChef = kits[0].kitType == "IonChefPrepKit"
        
        return isIonChef

    def isProton(self):
        selectedChipType = self.steps[StepNames.KITS].savedFields[KitsFieldNames.CHIP_TYPE]
        isProton = False
        
        if (selectedChipType):
            chips = Chip.objects.filter(name = selectedChipType, instrumentType__iexact = "proton")
            if chips:
                isProton = True
                
        return isProton 
            
    def isTargetStepAfterOriginal(self, original_step_name, target_step_name):
        if original_step_name == StepNames.EXPORT:
            return True
        if original_step_name == StepNames.SAVE_TEMPLATE or original_step_name == StepNames.SAVE_PLAN \
        or original_step_name == StepNames.SAVE_TEMPLATE_BY_SAMPLE or original_step_name == StepNames.SAVE_PLAN_BY_SAMPLE:
            return False
        
        original_index = self.steps.keys().index(original_step_name)
        target_index = self.steps.keys().index(target_step_name)
        return target_index >= original_index


    def getApplProduct(self):
        return self.steps[StepNames.APPLICATION].savedObjects[ApplicationFieldNames.APPL_PRODUCT]


    def isToMandateTargetTechniqueToShow(self):
        """
        this is a workaround until applproduct supports application-group sepecific rules
        """
        if self.getApplicationGroupName():
            savedApplGroup = self.steps[StepNames.APPLICATION].savedFields[ApplicationFieldNames.APPLICATION_GROUP];
            logger.debug("step_helper.isToMandateTargetTechniqueToShow() savedApplGroup=%s; applicationGroupName=%s" %(savedApplGroup, self.getApplicationGroupName()))
            return True if self.getApplicationGroupName() in ["DNA + RNA"] else False;
        else:
            return True

# 
#     def getApplProductByRunType(self, runTypeId):
#         applProducts = self.steps[StepNames.APPLICATION].prepopulatedFields[ApplicationFieldNames.APPL_PRODUCTS]
#         
#         for applProduct in applProducts:
#             if applProduct.applType_id == runTypeId:
#                 #logger.debug("step_helper.getApplProductByRunType() runTypeId=%s; going to return applProduct=%s" %(runTypeId, applProduct))
#                 return applProduct
#         return None
    

    def getRunTypeObject(self):
        logger.debug("getRunTypeObject nucleotideType=%s" %(self.steps[StepNames.APPLICATION].savedObjects[ApplicationFieldNames.RUN_TYPE].nucleotideType))
                
        #save_plan_step_data.savedFields[SavePlanFieldNames.SAMPLES_TABLE]
        return self.steps[StepNames.APPLICATION].savedObjects[ApplicationFieldNames.RUN_TYPE]

    def getApplicationGroupName(self):
        #logger.debug("ENTER getApplicationGroupName() applicationGroup=%s" %(self.steps[StepNames.APPLICATION].savedFields[ApplicationFieldNames.APPLICATION_GROUP]))
        #logger.debug("..getApplicationGroupName applicationGroupName=%s" %(self.steps[StepNames.APPLICATION].prepopulatedFields[ApplicationFieldNames.APPLICATION_GROUP_NAME]))
        
        #20150301-TODO- this may be fixed. Need to retest
        #20140401-BUG-could be None sometimes!! return self.steps[StepNames.APPLICATION].prepopulatedFields[ApplicationFieldNames.APPLICATION_GROUP_NAME]
        #20140401-WORKAROUND
        applicationGroupName = self.steps[StepNames.APPLICATION].prepopulatedFields[ApplicationFieldNames.APPLICATION_GROUP_NAME]
        return applicationGroupName if applicationGroupName else self.getSelectedApplicationGroupName()

   
    def isControlSeqTypeBySample(self):
        return self.getApplProduct().isControlSeqTypeBySampleSupported
    
    def isReferenceBySample(self):
        return self.getApplProduct().isReferenceBySampleSupported
    
    def isDualNucleotideTypeBySample(self):
        return self.getApplProduct().isDualNucleotideTypeBySampleSupported
    
    def isBarcodeKitSelectionRequired(self):
        return self.getApplProduct().isBarcodeKitSelectionRequired

    def isOCPEnabled(self):
        return isOCP_enabled()
   

    def isOCPApplicationGroup(self):
        return self.getApplicationGroupName() == "DNA + RNA"
    
                            
    def getNucleotideTypeList(self):
        return ["", "DNA", "RNA"]
    

    def getSelectedApplicationGroupName(self):
        #logger.debug("ENTER getSelectedApplicationGroupName...self.steps[StepNames.APPLICATION].savedFields=%s" %(self.steps[StepNames.APPLICATION].savedFields))

        value = self.steps[StepNames.APPLICATION].savedFields[ApplicationFieldNames.APPLICATION_GROUP]

        if value:
            applGroupObjs = ApplicationGroup.objects.filter(isActive = True).filter(id = value)
            if applGroupObjs:
                return applGroupObjs[0].name
        return ""
   
        
    def validateAll(self):
        for step_name, step in self.steps.items():
            # do not validate plan step if this is a template helper and vice versa
            if (self.isPlan() and step_name != StepNames.SAVE_TEMPLATE) or (self.isTemplate() and step_name != StepNames.SAVE_PLAN):         
                step.validate()
                if step.hasErrors():
                    logger.debug("step_helper.validateAll() HAS ERRORS! step_name=%s" %(step_name))                    
                    return step_name
        
        return None
        
    def getChangedFields(self):
        changed = {}
        for step in self.steps.values():
            for key, values in step._changedFields.items():
                if (values[0] or values[1]) and (values[0] != values[1]) and str(values[0] != values[1]):
                    changed[key] = values
        return changed
