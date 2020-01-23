import JsonHuman from 'json-human/src/json.human';
import linkifyElement from 'linkify-element';

window.render_json = function(props) {
    var node = JsonHuman.format(props.data);
    linkifyElement(node, { target: '_blank' });
    document.getElementById(props.divid).appendChild(node);
}
