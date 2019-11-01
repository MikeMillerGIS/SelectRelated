import arcpy

from un_editor_solutions import SelectRelated


class Toolbox(object):
    def __init__(self):
        """Define the toolbox (the name of the toolbox is the name of the
        .pyt file)."""
        self.label = "Utility Network Editor Tools"
        self.alias = "utilsol_Editor_Tools"

        # List of tool classes associated with this toolbox
        self.tools = [SelectRelatedRecords]


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

        relate_map = arcpy.Parameter(name='relate_map',
                                     displayName='Layer Relationship Map',
                                     datatype='GPValueTable',
                                     direction='Input',
                                     parameterType='Optional',
                                     enabled=None,
                                     category=None,
                                     symbology=None,
                                     multiValue=None)

        relate_map.columns = [['GPFeatureLayer', 'Source Layer'], ['Field', 'Source Key Field'],
                              ['GPFeatureLayer', 'Target Layer'], ['Field', 'Target Key Field']]
        # "{C99D0042-EF42-4B04-8A0B-1A53F6DB67A6}" -- proportional (no + sign and no separator)
        # "{1AA9A769-D3F3-4EB0-85CB-CC07C79313C8}"  # + sign and separator
        relate_map.controlCLSID = "{1AA9A769-D3F3-4EB0-85CB-CC07C79313C8}"
        return [relate_map]

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        return True

    def execute(self, parameters, messages):
        """The source code of the tool."""
        self.run()

    @staticmethod
    def run():
        SelectRelated().main()
