import 'bootstrap';
import 'bootstrap-tokenfield';
import 'jquery-validation';
import 'czmore';

$('#authors').tokenfield({});

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
    errorElement: 'span',
    errorClass: 'help-block',
    errorPlacement: function(error, element) {
        if(element.parent('.input-group').length) {
            error.insertAfter(element.parent());
        } else {
            error.insertAfter(element);
        }
    }
});

$("#czContainer").czMore({
    max: 5, styleOverride: true,
    onAdd: function(index) {
        $('.btnMinus').addClass('col-sm-1').html('<span class="glyphicon glyphicon-remove" aria-hidden="true"></span>');
    }
});
$('.btnPlus').html('<span class="glyphicon glyphicon-plus" style="top: 10px;" aria-hidden="true"></span>')
