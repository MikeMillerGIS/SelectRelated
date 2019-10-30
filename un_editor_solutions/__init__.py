import arcpy
import os
import pathlib


class SelectRelated(object):
    def __init__(self, utility_network, project='CURRENT', map=None):
        self.utility_network = utility_network
        self.project = project
        self.map = map

    @staticmethod
    def chunks(l, n):
        """Yield successive n-sized chunks from l."""
        for i in range(0, len(l), n):
            yield l[i:i + n]

    @staticmethod
    def create_sql(table: str, field: str, values) -> str:
        """ Creates an SQL query against input table of the form 'field IN (values)' or field = value """
        field_delim = arcpy.AddFieldDelimiters(table, field)
        chunk_value = 950

        if isinstance(values, (list, tuple, set)):
            if not values:
                return '1 = 1'
            query = '{} IN ({})'
            # Remove duplicates and sort for indexed fields
            values = sorted(set(values))
        else:
            query = '{} = {}'
            values = [values]

        # Wrap values in text-like fields so that expression is 'field op ("x", "y", "z")'
        if isinstance(values[0], str):
            # String can contain the wraping single quote, so it need to be converted
            # to two single quotes
            vals = [f"""'{v.replace("'", "''")}'""" for v in values]
        else:
            vals = list(map(str, values))
        for chunk_value in SelectRelated.chunks(vals, chunk_value):
            yield query.format(field_delim, ",".join(chunk_value))

    def get_workspace(self, layer_path):

        desc = arcpy.Describe(str(pathlib.Path(layer_path).parent))
        if desc.dataType == 'FeatureDataset':
            return pathlib.Path(desc.catalogPath).parent
        return pathlib.Path(desc.catalogPath)

    def rc_info(self, layer):
        desc = arcpy.Describe(layer)
        if not desc.relationshipClassNames:
            return None
        workspace = self.get_workspace(desc.catalogPath)
        rc_class_info = {}
        for rc_name in desc.relationshipClassNames:
            rc = str(workspace / rc_name)
            if arcpy.Exists(rc):
                rc_desc = arcpy.Describe(rc)
                if rc_desc.isAttachmentRelationship:
                    continue
                for cls in rc_desc.originClassNames:
                    if cls == desc.name:
                        continue
                    rc_class_info[cls] = [cl_key[0] for cl_key in rc_desc.originClassKeys if cl_key[1] == 'OriginPrimary'][0]
                for cls in rc_desc.destinationClassNames:
                    if cls == desc.name:
                        continue
                    rc_class_info[cls] = [cl_key[0] for cl_key in rc_desc.originClassKeys if cl_key[1] == 'OriginForeign'][0]
        return rc_class_info

    def main(self):
        # get the current project and map
        project = arcpy.mp.ArcGISProject(self.project)
        if not self.map:
            map = project.activeMap
        else:
            map = project.listMaps(wildcard=self.map)[-1]
        if not map:
            print("Open and activate a map")
            return

        cim_lookup = {}
        layers = map.listLayers()
        for layer in layers:
            cim_def = layer.getDefinition('V2')
            cim_lookup[cim_def.uRI] = layer

        cims_processed = []
        fields = ['GlobalID']
        for layer in layers:
            rc_info = self.rc_info(layer)
            cim_def = layer.getDefinition('V2')
            if cim_def.uRI in cims_processed:
                continue
            GlobalIDs = set()
            if isinstance(cim_def, arcpy.cim.CIMVectorLayers.CIMSubtypeGroupLayer):
                for sub_layer_cim in cim_def.subtypeLayers:
                    cims_processed.append(sub_layer_cim)
                    if cim_lookup[sub_layer_cim].getSelectionSet() is not None:
                        GlobalIDs.update({row[0] for row in arcpy.da.SearchCursor(cim_lookup[sub_layer_cim], fields)})

            else:
                cims_processed.append(cim_def.uRI)
                if layer.getSelectionSet() is not None:
                    GlobalIDs = {row[0] for row in arcpy.da.SearchCursor(layer, fields)}
            if GlobalIDs:
                print(f'{cim_def.name}: found {len(GlobalIDs)} global ids.')


if __name__ == '__main__':
    SelectRelated(utility_network="Electric Utility Network",
                  project="C:\_MyFiles\github\SelectRelateRecords\sample\SelectRelated.aprx", map="Map").main()
