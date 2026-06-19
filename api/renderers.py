from rest_framework_xml.renderers import XMLRenderer


class AutoPkgXMLRenderer(XMLRenderer):
    root_tag_name = 'response'
    item_tag_name = 'item'
