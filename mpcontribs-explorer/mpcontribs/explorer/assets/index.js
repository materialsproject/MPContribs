import 'bootstrap';
import 'jquery.spin';
import 'chosen';

$(document).ready(function() {
    $("#spinner").spin('small');
    $('select').chosen({
        search_contains: true, allow_single_deselect: true, width: "100%"
    });
    $('#explorer_form').show();
    $("#spinner").spin(false);
});
