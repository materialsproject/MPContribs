import 'bootstrap';
import 'bootstrap-tokenfield';
import 'jquery-validation';

$('#authors').tokenfield();

$.validator.addMethod("alphanumeric", function(value, element) {
    return this.optional(element) || /^[\w_]+$/i.test(value);
}, "Please use letters, numbers, and underscores only.");

$('#apply-form').validate({
    rules: {project: {alphanumeric: true}},
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
