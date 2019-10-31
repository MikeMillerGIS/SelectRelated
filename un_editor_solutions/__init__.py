import arcpy
import os
import pathlib


class SelectRelated(object):
    def __init__(self, project='CURRENT', pro_map=None):
        self.project = project
        self.pro_map = pro_map

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

    def rc_info(self, layer):
        rc_class_info = {}
        desc = arcpy.Describe(layer)
        if hasattr(desc, 'FeatureClass') is False or desc.FeatureClass.dataType != 'FeatureClass':
            return rc_class_info
        if not desc.relationshipClassNames:
            return rc_class_info
        workspace = self.get_workspace(desc.catalogPath)
        for rc_name in desc.relationshipClassNames:
            rc = str(workspace / rc_name)
            if arcpy.Exists(rc):
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
                    rc_class_info[cls] = {cl_key[1]: cl_key[0] for cl_key in rc_desc.originClassKeys}
        return rc_class_info

    def main(self):
        # get the current project and map
        project = arcpy.mp.ArcGISProject(self.project)
        if not self.pro_map:
            pro_map = project.activeMap
        else:
            pro_map = project.listMaps(wildcard=self.pro_map)[-1]
        if not pro_map:
            print("Open and activate a map")
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
            # Update the progressor label for layer
            arcpy.SetProgressorLabel(f"Evaluating selection set on {layer.name}")

            cim_def = layer.getDefinition('V2')
            # Add Tables and Feature layers to the datasource lookup
            if hasattr(layer, 'isFeatureLayer') is False or layer.isFeatureLayer:
                datasource_lookup.setdefault(layer.connectionProperties['dataset'], []).append(layer)

            # If the layer was already processed as part of a subtype layer, do not re-evaul
            if cim_def.uRI in cims_processed:
                # Update the progressor position
                arcpy.SetProgressorPosition()
                continue

            # Get the related class and its foreign ID
            rc_info = self.rc_info(layer=layer)
            # if there is not relationship, move to next layer
            if not rc_info:
                # Update the progressor position
                arcpy.SetProgressorPosition()
                continue
            parent_ids = set()
            if isinstance(cim_def, arcpy.cim.CIMVectorLayers.CIMSubtypeGroupLayer):
                # If it is a subtype layer, check the selection of all sublayers and collect primary key of the features
                for sub_layer in layer.listLayers():
                    cim_def_sub = sub_layer.getDefinition('V2')
                    # If the layer was already processed as part of a subtype layer, do not re-evaul
                    if cim_def_sub.uRI in cims_processed:
                        continue
                    cims_processed.append(cim_def_sub.uRI)
                    if sub_layer.getSelectionSet() is not None:
                        fields = list({v['OriginPrimary'].lower() for k, v in rc_info.items()})
                        parent_ids.update({row[0] for row in arcpy.da.SearchCursor(sub_layer, fields)})

            else:
                # Collect the primary key of the features
                cims_processed.append(cim_def.uRI)
                if layer.getSelectionSet() is not None:
                    fields = [v['OriginPrimary'] for k, v in rc_info.items()]
                    parent_ids = {row[0] for row in arcpy.da.SearchCursor(layer, fields)}

            if parent_ids:
                print(f'{cim_def.name}: found {len(parent_ids)} parent ids.')
                for k, v in rc_info.items():
                    selection_info.setdefault(k, {'field': v['OriginForeign'], 'ids': set()})['ids'].update(parent_ids)
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
            if count:
                arcpy.AddMessage(f'Selecting {count} rows in {related_layer.name}')
            # Update the progressor position
            arcpy.SetProgressorPosition()
        if missing_related:
            arcpy.AddWarning(f'The following related classes are missing from the map: {missing_related}')


if __name__ == '__main__':
    SelectRelated(project="C:\_MyFiles\github\SelectRelateRecords\sample\SelectRelated.aprx",
                  pro_map="Map").main()
