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
            pro_map = project.listMaps(wildcard=self.map)[-1]
        if not pro_map:
            print("Open and activate a map")
            return
        # Loop through all the layers and table
        # build a lookup to layers by CIM so subtype layers can be evaluated together
        # Build a layer lookup to apply selection set against
        cim_lookup = {}
        datasource_lookup = {}
        layers = pro_map.listLayers()
        tables = pro_map.listTables()
        for layer in layers + tables:
            cim_def = layer.getDefinition('V2')
            cim_lookup[cim_def.uRI] = layer

            if isinstance(cim_def,
                          (arcpy.cim.CIMVectorLayers.CIMFeatureLayer,
                           arcpy.cim.CIMVectorLayers.CIMSubtypeGroupLayer,
                           arcpy.cim.CIMVectorLayers.CIMStandaloneTable)):
                if hasattr(cim_def, 'featureTable'):
                    datasource_lookup.setdefault(cim_def.featureTable.dataConnection.dataset, []).append(layer)
                elif hasattr(cim_def, 'dataConnection'):
                    datasource_lookup.setdefault(cim_def.dataConnection.dataset, []).append(layer)

        cims_processed = []
        for layer in layers:
            cim_def = layer.getDefinition('V2')
            # If the layer was already processed as part of a subtype layer, do not re-evaul
            if cim_def.uRI in cims_processed:
                continue
            # Get the related class and its foreign ID
            rc_info = self.rc_info(layer=layer)
            # if there is not relationship, move to next layer
            if not rc_info:
                continue
            parent_ids = set()
            if isinstance(cim_def, arcpy.cim.CIMVectorLayers.CIMSubtypeGroupLayer):
                # If it is a subtype layer, check the selection of all sublayers and collect primary key of the features
                for sub_layer_cim in cim_def.subtypeLayers:
                    cims_processed.append(sub_layer_cim)
                    if cim_lookup[sub_layer_cim].getSelectionSet() is not None:
                        fields = list({v['OriginPrimary'].lower() for k, v in rc_info.items()})
                        parent_ids.update({row[0] for row in arcpy.da.SearchCursor(cim_lookup[sub_layer_cim], fields)})

            else:
                # Collect the primary key of the features
                cims_processed.append(cim_def.uRI)
                if layer.getSelectionSet() is not None:
                    fields = [v['OriginPrimary'] for k, v in rc_info.items()]
                    parent_ids = {row[0] for row in arcpy.da.SearchCursor(layer, fields)}

            if parent_ids:
                print(f'{cim_def.name}: found {len(parent_ids)} parent ids.')
                for k, v in rc_info.items():
                    if k not in datasource_lookup:
                        # Related class not in the map
                        continue
                    # TODO: What to do with multi layers
                    related_layer = datasource_lookup[k][0]
                    count = 0
                    for where_clause in self.create_sql(related_layer, v['OriginForeign'], parent_ids):
                        oids = [row[0] for row in arcpy.da.SearchCursor(related_layer, ['objectid'], where_clause)]
                        related_layer.setSelectionSet(oidList=oids, method='UNION')
                        count += len(oids)
                    if count:
                        arcpy.AddMessage(f'Selecting {count} rows in {related_layer.name}')


if __name__ == '__main__':
    SelectRelated(project="C:\_MyFiles\github\SelectRelateRecords\sample\SelectRelated.aprx",
                  pro_map="Map").main()
