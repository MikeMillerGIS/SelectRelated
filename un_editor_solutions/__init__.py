from functools import lru_cache
from typing import Dict
from operator import itemgetter
import arcpy
import os
import pathlib
import re


class SelectRelated(object):
    def __init__(self, project='CURRENT', map_name=None):
        self.project = project
        self.map_name = map_name
        self.pattern = re.compile(r'L(\d+).*')

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

    @staticmethod
    def get_workspace(layer_path):

        desc = arcpy.Describe(str(pathlib.Path(layer_path).parent))
        if desc.dataType == 'FeatureDataset':
            return pathlib.Path(desc.catalogPath).parent
        return pathlib.Path(desc.catalogPath)

    @lru_cache()
    def describe_workspace(self, workspace):
        return arcpy.Describe(workspace)

    def rc_info(self, layer):
        rc_class_info = {}
        print(layer)
        desc = arcpy.Describe(layer)
        if hasattr(desc, 'FeatureClass') is False or desc.FeatureClass.dataType != 'FeatureClass':
            return rc_class_info
        if not desc.relationshipClassNames:
            return rc_class_info
        if str(desc.path).startswith('http'):
            workspace = desc.path
            workspace_desc = self.describe_workspace(workspace.lower())
            workspace_lookup = {child.name: child for child in workspace_desc.children}
            for rc_name in desc.relationshipClassNames:
                if rc_name not in workspace_lookup:
                    continue
                rc_desc = workspace_lookup[rc_name]
                if rc_desc.isAttachmentRelationship:
                    continue
                # Note: Commented out as only supporting Origin selections pushed to Destinations **
                # for cls in rc_desc.originClassNames:
                #     if cls == desc.name:
                #         continue
                #     rc_class_info[cls] = \
                #     [cl_key[0] for cl_key in rc_desc.originClassKeys if cl_key[1] == 'OriginPrimary'][0]
                for cls in rc_desc.destinationClassNames:
                    layer_id = self.pattern.findall(cls)[0]
                    if layer_id == desc.name:
                        continue
                    # rc_class_info.setdefault(layer_id, []).append(
                    #    {cl_key[1]: cl_key[0] for cl_key in rc_desc.originClassKeys})
                    rc_class_info[layer_id] = {cl_key[1]: cl_key[0] for cl_key in rc_desc.originClassKeys}
        else:
            workspace = self.get_workspace(desc.catalogPath)
            for rc_name in desc.relationshipClassNames:
                rc = str(workspace / rc_name)
                if not arcpy.Exists(rc):
                    continue
                rc_desc = arcpy.Describe(rc)
                if rc_desc.isAttachmentRelationship:
                    continue
                # Note: Commented out as only supporting Origin selections pushed to Destinations **
                # for cls in rc_desc.originClassNames:
                #     if cls == desc.name:
                #         continue
                #     rc_class_info[cls] = \
                #     [cl_key[0] for cl_key in rc_desc.originClassKeys if cl_key[1] == 'OriginPrimary'][0]
                for cls in rc_desc.destinationClassNames:
                    if cls == desc.name:
                        continue
                    # rc_class_info.setdefault(cls, []).append(
                    #    {cl_key[1]: cl_key[0] for cl_key in rc_desc.originClassKeys})
                    rc_class_info[cls] = {cl_key[1]: cl_key[0] for cl_key in rc_desc.originClassKeys}

        return rc_class_info

    @staticmethod
    def merge_dols(dol1, dol2):
        # https://stackoverflow.com/questions/1495510/combining-dictionaries-of-lists-in-python
        keys = set(dol1).union(dol2)
        no = []
        return dict((k, dol1.get(k, no) + dol2.get(k, no)) for k in keys)

    @staticmethod
    def rows_as_dicts(cursor):
        col_names = cursor.fields
        for row in cursor:
            yield dict(zip(col_names, row))

    def main(self, relate_map):
        # get the current project and map
        project = arcpy.mp.ArcGISProject(self.project)
        pro_map = None
        if not self.map_name:
            pro_map = project.activeMap
        else:
            maps = project.listMaps(wildcard=self.map_name)
            if maps:
                pro_map = maps[-1]
        if not pro_map:
            print("Map could not be found")
            return

        # Dict to lookup layer by datasource
        datasource_lookup = {}
        cims_processed = []
        selection_info = {}
        missing_related = set()
        # Loop through all the layers and table
        layers = pro_map.listLayers()
        tables = pro_map.listTables()
        # Set the progressor
        arcpy.SetProgressor("step", "Reviewing selected features", 0, len(layers + tables), 1)
        for layer in layers + tables:
            if layer.isBroken:
                arcpy.AddWarning(f'{layer} is broken')
                continue
            # Update the progressor label for layer
            arcpy.SetProgressorLabel(f"Evaluating selection set on {layer.name}")

            cim_def = layer.getDefinition('V2')
            # Add Tables and Feature layers to the datasource lookup
            if hasattr(layer, 'isFeatureLayer') is False or layer.isFeatureLayer:
                datasource_lookup.setdefault(layer.connectionProperties['dataset'], []).append(layer)
                datasource_lookup.setdefault(layer.name, []).append(layer)

            # If the layer was already processed as part of a subtype layer, do not re-evaul
            if cim_def.uRI in cims_processed:
                # Update the progressor position
                arcpy.SetProgressorPosition()
                continue
            if relate_map:
                if layer.name not in relate_map:
                    continue
                rc_info = relate_map[layer.name]
            else:
                # Get the related class and its foreign ID
                rc_info = self.rc_info(layer=layer)
            # if there is not relationship, move to next layer
            if not rc_info:
                # Update the progressor position
                arcpy.SetProgressorPosition()
                continue
            parent_ids = {}
            if isinstance(cim_def, arcpy.cim.CIMVectorLayers.CIMSubtypeGroupLayer):
                # If it is a subtype layer, check the selection of all sublayers and collect primary key of the features
                fields = list({v['OriginPrimary'].lower() for k, v in rc_info.items()})
                for sub_layer in layer.listLayers():
                    cim_def_sub = sub_layer.getDefinition('V2')
                    # If the layer was already processed as part of a subtype layer, do not re-evaul
                    if cim_def_sub.uRI in cims_processed:
                        continue
                    cims_processed.append(cim_def_sub.uRI)
                    if sub_layer.getSelectionSet() is not None:
                        with arcpy.da.SearchCursor(sub_layer, fields) as cursor:
                            ids = dict(zip(fields, zip(*cursor)))
                            for field in fields:
                                parent_ids.setdefault(field, []).extend(list(ids[field]))
            else:
                # Collect the primary key of the features
                cims_processed.append(cim_def.uRI)
                if layer.getSelectionSet() is not None:
                    fields = list({v['OriginPrimary'].lower() for k, v in rc_info.items()})
                    with arcpy.da.SearchCursor(layer, fields) as cursor:
                        parent_ids = dict(zip(fields, zip(*cursor)))
            # As the result is a collection of values by field, get a arbitrary field and count its values for a count
            select_count = len(next(iter(parent_ids.values())))
            if select_count:
                print(f'{cim_def.name}: found {select_count} parent ids.')
                for k, v in rc_info.items():
                    selection_info.setdefault(k, {'field': v['OriginForeign'], 'ids': set()})['ids'].update(
                        parent_ids[v['OriginPrimary'].lower()])
            # Update the progressor position
            arcpy.SetProgressorPosition()

        # Set the progressor
        arcpy.SetProgressor("step", "Selecting related features", 0, len(selection_info.keys()), 1)
        for k, v in selection_info.items():
            # Update the progressor label for layer
            arcpy.SetProgressorLabel(f"Selecting rows in {k}")
            if k not in datasource_lookup:
                # Related class not in the map
                missing_related.add(k)
                # Update the progressor position
                arcpy.SetProgressorPosition()
                continue
            # TODO: What to do with multi layers
            related_layer = datasource_lookup[k][0]
            count = 0
            for where_clause in self.create_sql(related_layer, v['field'], v['ids']):
                oids = [row[0] for row in arcpy.da.SearchCursor(related_layer, ['objectid'], where_clause)]
                related_layer.setSelectionSet(oidList=oids, method='UNION')
                count += len(oids)
            arcpy.AddMessage(f'Selecting {count} rows in {related_layer.name}')
            # Update the progressor position
            arcpy.SetProgressorPosition()
        if missing_related:
            arcpy.AddWarning(f'The following related classes are missing from the map: {missing_related}')


if __name__ == '__main__':
    relate_map_test = {
        'Electric Device': {
            'ElectricDeviceUnit': {
                'OriginPrimary': 'GlobalID',
                'OriginForeign': 'relateddevice'
            }}}
    relate_map_test = {
        'Electric Device': {
            'Device Unit': {
                'OriginPrimary': 'GlobalID',
                'OriginForeign': 'relateddevice'
            }}}
    map_name = "Electric_FGDB"
    map_name = "Electric_FGDB_all"
    map_name = "Electric Network Editor"

    relate_map_test = relate_map_test
    SelectRelated(project=r"C:\_MyFiles\github\SelectRelateRecords\sample\SelectRelated.aprx",
                  map_name=map_name).main(relate_map=relate_map_test)
