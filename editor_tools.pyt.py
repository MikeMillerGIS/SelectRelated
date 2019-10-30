import logging
import os
import pathlib
from datetime import datetime
from typing import List

import arcpy


[logging.getLogger(x).setLevel('DEBUG') for x in ['utility_solutions', 'untools']]

class Toolbox(object):
    def __init__(self):
        """Define the toolbox (the name of the toolbox is the name of the
        .pyt file)."""
        self.label = "Utility Network Editor Tools"
        self.alias = "utilsol_Editor_Tools"

        # List of tool classes associated with this toolbox
        self.tools = []


class SelectRelatedRecords(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Select Related Records"
        self.description = "Select Releated Records"
        self.category = ""
        self.canRunInBackground = False

    def getParameterInfo(self):
        """Define parameter definitions"""
        return []

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        return True

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        return True

    def execute(self, parameters, messages):
        """The source code of the tool."""
        self.run()

    @staticmethod
    def run():
        pass
