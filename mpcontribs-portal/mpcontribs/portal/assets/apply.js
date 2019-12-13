import 'bootstrap';
import 'bootstrap-tokenfield';
import 'jquery-form';
import 'jquery-validation';
import 'czmore';

$('#authors').tokenfield({});

function prepareRequest(formData, jqForm, options) {
    $('.alert-success').hide();
    $('.alert-danger').hide();
    var start = 5;
    var nrefs = parseInt(formData.splice(start, 1)[0]['value']);
    if (nrefs < 1) {
        $('.alert-danger').html('Please add references.').show();
        return false;
    }
    for (var i = 0; i < nrefs; i++) {
        var key_url = formData.splice(start+i, 2);
        formData.splice(start+i, 0, {'name': key_url[0]['value'], 'value': key_url[1]['value']});
    }
    return true;
}

$.validator.addMethod("alphanumeric", function(value, element) {
    return this.optional(element) || /^[\w_]+$/i.test(value);
}, "Please use letters, numbers, and underscores only.");

$('#apply-form').validate({
    rules: {
        project: {alphanumeric: true},
        url_1: {url: true, required: true},
        url_2: {url: true},
        url_3: {url: true},
        url_4: {url: true},
        url_5: {url: true}
    },
    highlight: function (element) {
        $(element).nextAll('.glyphicon').removeClass('glyphicon-ok').addClass('glyphicon-remove');
        $(element).closest('.form-group').removeClass('has-success').addClass('has-error');
    },
    unhighlight: function (element) {
        $(element).nextAll('.glyphicon').removeClass('glyphicon-remove').addClass('glyphicon-ok');
        $(element).closest('.form-group').removeClass('has-error').addClass('has-success');
    },
    errorElement: 'span', errorClass: 'help-block',
    errorPlacement: function(error, element) {
        if(element.parent('.input-group').length) {
            error.insertAfter(element.parent());
        } else { error.insertAfter(element); }
    },
    submitHandler: function(form) { $(form).ajaxSubmit({
        //target: '#output', // update with server response, use for ok message next to button
        beforeSubmit: prepareRequest,
        //success: processJson, // anything to do?
        url: window.api['host'] + 'projects/',
        type: 'POST', dataType: 'json',
        //clearForm: true, // after successful submit
        //resetForm: true
    }); },
    //invalidHandler: function(event, validator) {
    //    // 'this' refers to the form
    //    var errors = validator.numberOfInvalids();
    //    // TODO check default invalidHandler in code
    //}
});

$("#czContainer").czMore({
    max: 5, styleOverride: true,
    onAdd: function(index) {
        $('.btnMinus').addClass('col-sm-1').html('<span class="glyphicon glyphicon-remove" aria-hidden="true"></span>');
    }
});
$('.btnPlus').html('<span class="glyphicon glyphicon-plus" style="top: 10px;" aria-hidden="true"></span>')
