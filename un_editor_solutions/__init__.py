import arcpy


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

    def _related_tables_url(self, service_url: str):

        des = arcpy.Describe(service_url)
        rc = {}
        fc = {}
        tb = {}
        for child in des.children:
            if child.dataType == "FeatureClass":
                fc[child.name] = child
            elif child.dataType == "RelationshipClass":
                rc[child.name] = child

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

        feature_layers = {}
        for layer in layers:
            cim_def = layer.getDefinition('V2')
            if isinstance(cim_def, arcpy.cim.CIMVectorLayers.CIMSubtypeGroupLayer):
                desc = arcpy.Describe(layer)
                oid_field_name = desc.OIDFieldName
                oids = set()
                for sub_layer in cim_def.subtypeLayers:
                    selection_set = cim_lookup[sub_layer].getSelectionSet()
                    if selection_set:
                        oids.update(selection_set)
                    #cim_lookup[sub_layer] = {'data_source': layer.dataSource}
                where_clauses = None
                if oids:
                    where_clauses = SelectRelated.create_sql(layer, oid_field_name, oids)
                cim_lookup[sub_layer] = {'data_source': layer.dataSource,
                                         'where': where_clauses}
            else:
                cim_lookup[cim_def.uRI] = {'data_source': layer.dataSource}

        # self._related_tables_url(un_layer)

        for subtype_layer, layers_cims in subtype_layers.items():
            oids = []
            oid_field_name = None
            for layer_cim in layers_cims:
                layer = cim_lookup[layer_cim]
                desc = arcpy.Describe(layer)
                if not oid_field_name:
                    oid_field_name = desc.OIDFieldName
                fidSet = desc.FIDSet
                if not fidSet:
                    continue
                fidList = fidSet.replace(' ', '').split(';')
                oids.extend(fidList)
            if not oids:
                continue
            where_clauses = SelectRelated.create_sql(subtype_layer, oid_field_name, oids)
            for where_clause in where_clauses:
                arcpy.SelectLayerByAttribute_management(inView, 'ADD_TO_SELECTION', whereClause)


if __name__ == '__main__':
    SelectRelated(utility_network="Electric Utility Network",
                  project="C:\_MyFiles\github\SelectRelateRecords\sample\SelectRelated.aprx", map="Map").main()
