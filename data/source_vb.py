from data.source import Source
import requests
import json
import _config as config


class VbAuthException(Exception):
    pass


class VbException(Exception):
    pass


class VB(Source):
    CONCEPT_HERARCHY = {}

    def __init__(self, vocab_id):
        self.vocab_id = vocab_id
        s = requests.session()
        r = s.post(
            config.VB_ENDPOINT + '/Auth/login',
            data={
                'email': config.VB_USER,
                'password': config.VB_PASSWORD
            }
        )
        if r.status_code == 200:
            self.s = s
        else:
            raise VbAuthException('Not able to log in. Error from VB is: ' + r.content.decode('utf-8'))

    def list_vocabularies(self):
        r = self.s.get(config.VB_ENDPOINT + '/Projects/listProjects', params={'consumer': 'SYSTEM'})
        if r.status_code == 200:
            d = json.loads(r.content.decode('utf-8'))

            return [(v['baseURI'], v['name']) for v in d['result']]
        else:
            raise VbException('There was an error: ' + r.content.decode('utf-8'))

    def list_collections(self):
        r = self.s.post(
            config.VB_ENDPOINT + '/SPARQL/evaluateQuery',
            data={
                'query':
                    '''PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
                    SELECT *
                    WHERE {
                      ?c a skos:Collection ;
                         skos:prefLabel ?pl .
                    }''',
                'ctx_project': self.vocab_id
            }
        )
        concepts = json.loads(r.content.decode('utf-8'))['result']['sparql']['results']['bindings']
        if r.status_code == 200:
            return [(x.get('c').get('value'), x.get('pl').get('value')) for x in concepts]
        else:
            raise VbException('There was an error: ' + r.content.decode('utf-8'))

    def list_concepts(self):
        r = self.s.post(
            config.VB_ENDPOINT + '/SPARQL/evaluateQuery',
            data={
                'query':
                    '''PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
                    SELECT *
                    WHERE {
                      ?c a skos:Concept ;
                         skos:prefLabel ?pl .
                    }''',
                'ctx_project': self.vocab_id
            }
        )
        concepts = json.loads(r.content.decode('utf-8'))['result']['sparql']['results']['bindings']
        if r.status_code == 200:
            return [(x.get('c').get('value'), x.get('pl').get('value')) for x in concepts]
        else:
            raise VbException('There was an error: ' + r.content.decode('utf-8'))

    def get_vocabulary(self):
        r = self.s.post(
            config.VB_ENDPOINT + '/SPARQL/evaluateQuery',
            data={
                'query':
                    '''PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
                    PREFIX dct: <http://purl.org/dc/terms/>
                    PREFIX owl: <http://www.w3.org/2002/07/owl#>
                    SELECT *
                    WHERE {
                      ?s a skos:ConceptScheme ;
                      skos:prefLabel ?t .
                      OPTIONAL {?s dct:description ?d }
                      OPTIONAL {?s dct:creator ?c }
                      OPTIONAL {?s dct:created ?cr }
                      OPTIONAL {?s dct:modified ?m }
                      OPTIONAL {?s owl:versionInfo ?v }
                    }''',
                'ctx_project': self.vocab_id
            }
        )

        if r.status_code == 200:
            metadata = json.loads(r.content.decode('utf-8'))['result']['sparql']['results']['bindings'][0]

            concept_hierarchy = self._get_concept_hierarchy(str(metadata['s']['value']))

            from model.vocabulary import Vocabulary
            return Vocabulary(
                self.vocab_id,
                metadata['s']['value'],
                metadata['t']['value'],
                metadata['d']['value'] if metadata.get('d') is not None else None,
                metadata.get('c').get('value') if metadata.get('c') is not None else None,
                metadata.get('cr').get('value') if metadata.get('cr') is not None else None,
                metadata.get('m').get('value') if metadata.get('m') is not None else None,
                metadata.get('v').get('value') if metadata.get('v') is not None else None,
                conceptHierarchy=concept_hierarchy
            )
        else:
            raise VbException('There was an error: ' + r.content.decode('utf-8'))

    def get_collection(self, uri):
        pass

    def get_concept(self, uri):
        q = '''PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
            SELECT *
            WHERE {{
              <{0}> skos:prefLabel ?pl .
              OPTIONAL {{<{0}> skos:definition ?d }}
            }}'''.format(uri)
        r = self.s.post(
            config.VB_ENDPOINT + '/SPARQL/evaluateQuery',
            data={
                'query': q,
                'ctx_project': self.vocab_id
            }
        )
        metadata = json.loads(r.content.decode('utf-8'))['result']['sparql']['results']['bindings'][0]

        # get the concept's altLabels
        q = '''PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
            SELECT *
            WHERE {{
              <{}> skos:altLabel ?al .
            }}'''.format(uri)
        r = self.s.post(
            config.VB_ENDPOINT + '/SPARQL/evaluateQuery',
            data={
                'query': q,
                'ctx_project': self.vocab_id
            }
        )
        altLabels = json.loads(r.content.decode('utf-8'))['result']['sparql']['results']['bindings']

        # get the concept's hiddenLabels
        q = '''PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
            SELECT *
            WHERE {{
              <{}> skos:hiddenLabel ?hl .
            }}'''.format(uri)
        r = self.s.post(
            config.VB_ENDPOINT + '/SPARQL/evaluateQuery',
            data={
                'query': q,
                'ctx_project': self.vocab_id
            }
        )
        hiddenLabels = json.loads(r.content.decode('utf-8'))['result']['sparql']['results']['bindings']

        # get the concept's broaders
        q = ''' PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
            SELECT *
            WHERE {{
              <{}> skos:broader ?b .
              ?b skos:prefLabel ?pl .
            }}'''.format(uri)
        r = self.s.post(
            config.VB_ENDPOINT + '/SPARQL/evaluateQuery',
            data={
                'query': q,
                'ctx_project': self.vocab_id
            }
        )
        broaders = json.loads(r.content.decode('utf-8'))['result']['sparql']['results']['bindings']

        # get the concept's narrowers
        q = '''PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
            SELECT *
            WHERE {{
              <{}> skos:narrower ?n .
              ?n skos:prefLabel ?pl .
            }}'''.format(uri)
        r = self.s.post(
            config.VB_ENDPOINT + '/SPARQL/evaluateQuery',
            data={
                'query': q,
                'ctx_project': self.vocab_id
            }
        )
        narrowers = json.loads(r.content.decode('utf-8'))['result']['sparql']['results']['bindings']

        from model.concept import Concept
        return Concept(
            self.vocab_id,
            uri,
            metadata['pl']['value'],
            metadata.get('d').get('value') if metadata.get('d') is not None else None,
            [x.get('al').get('value') for x in altLabels],
            [x.get('hl').get('value') for x in hiddenLabels],
            metadata.get('sc').get('value') if metadata.get('sc') is not None else None,
            metadata.get('cn').get('value') if metadata.get('cn') is not None else None,
            [{'uri': x.get('b').get('value'), 'prefLabel': x.get('pl').get('value')} for x in broaders],
            [{'uri': x.get('n').get('value'), 'prefLabel': x.get('pl').get('value')} for x in narrowers],
            None  # TODO: replace Sem Properties sub
        )

    # returns an ordered list of tuples, (hierarchy level, Concept URI, Concept prefLabel)
    def _get_concept_hierarchy(self, concept_scheme_uri):
        r = self.s.post(
            config.VB_ENDPOINT + '/SPARQL/evaluateQuery',
            data={
                'query':
                    '''
                    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>

                    SELECT (COUNT(?mid) AS ?length) ?c ?pl ?parent
                    WHERE {{ 
                        ?c      a                                       skos:Concept .   
                        ?cs     (skos:hasTopConcept | skos:narrower)*   ?mid .
                        ?mid    (skos:hasTopConcept | skos:narrower)+   ?c .                      
                        ?c      skos:prefLabel                          ?pl .
                        ?c		(skos:topConceptOf | skos:broader)		?parent .
                        FILTER (?cs = <{}>)
                    }}
                    GROUP BY ?c ?pl ?parent
                    ORDER BY ?length ?parent ?pl'''.format(concept_scheme_uri),
                'ctx_project': self.vocab_id
            }
        )

        if r.status_code == 200:
            cs = json.loads(r.content.decode('utf-8'))['result']['sparql']['results']['bindings']
            hierarchy = []
            previous_parent_uri = None
            last_index = 0

            for c in cs:
                # insert all topConceptOf directly
                if str(c['c']['value']) == concept_scheme_uri:
                    hierarchy.append((
                        int(c['length']['value']),
                        c['c']['value'],
                        c['pl']['value']
                    ))
                else:
                    # If this is not a topConcept, see if it has the same URI as the previous inserted Concept
                    # If so, use that Concept's index + 1
                    this_parent = str(c['parent']['value'])
                    if this_parent == previous_parent_uri:
                        # use last inserted index
                        hierarchy.insert(last_index + 1, (
                            int(c['length']['value']),
                            c['c']['value'],
                            c['pl']['value']
                        ))
                        last_index += 1
                    # This is not a TopConcept and it has a differnt parent from the previous insert
                    # So insert it after it's parent
                    else:
                        i = 0
                        parent_index = 0
                        for t in hierarchy:
                            if this_parent in t:
                                parent_index = i
                            i += 1

                        hierarchy.insert(parent_index + 1, (
                            int(c['length']['value']),
                            c['c']['value'],
                            c['pl']['value']
                        ))

                        last_index = parent_index + 1
                    previous_parent_uri = this_parent

            return hierarchy
        else:
            raise VbException('There was an error: ' + r.content.decode('utf-8'))

    def _add_to_hierarchy(self, concept_uri, concept_pref_label , parent_uri):
        # if the concept's not in the hierarchy, recurse through parents until an ancestor is then add all the
        # intermediates
        if self.CONCEPT_HERARCHY.get(parent_uri) is not None:
            pass

    def get_object_class(self, uri):
        """Gets the class of the object.

        Classes restricted to being one of voaf:Vocabulary, skos:ConceptScheme, skos:Collection or skos:Collection

        :param uri: the URI of the object

        :return: the URI of the class of the object
        :rtype: :class:`string`
        """
        q = '''
            SELECT ?c
            WHERE {{
                <{}> a ?c .
            }}
        '''.format(uri)
        r = self.s.post(
            config.VB_ENDPOINT + '/SPARQL/evaluateQuery',
            data={
                'query': q,
                'ctx_project': self.vocab_id
            }
        )

        for c in json.loads(r.content.decode('utf-8'))['result']['sparql']['results']['bindings']:
            if c.get('c')['value'] in self.VOC_TYPES:
                return c.get('c')['value']

        return None


if __name__ == '__main__':
    VB('Test_Rock_Types_Vocabulary').get_concept_hierarchy('http://pid.geoscience.gov.au/def/voc/test-rock-types/conceptScheme')

