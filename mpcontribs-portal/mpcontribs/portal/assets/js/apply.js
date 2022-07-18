import "parsley";

const form = $("#apply-form");

if (form.length) {
    form.parsley({
        errorClass: "is-danger", successClass: "is-primary",
        errorsWrapper: '<ul class="parsley-errors-list is-size-7"></ul>'
    });
    form.on("submit", function(e) {
        e.preventDefault();
        $('#apply-button').addClass('is-loading');
        $('#apply-response').addClass('is-hidden');
        var data = Object.fromEntries(new FormData(e.target).entries());
        data["references"] = [
            {"label": data["ref_label"], "url": data["ref_url"]}
        ];
        delete data["ref_label"];
        delete data["ref_url"];
        data["license"] = $('#license :selected').val();
        $.post({
            url: window.api['host'] + 'projects/',
            headers: window.api['headers'],
            data: JSON.stringify(data),
            dataType: "json", contentType: 'application/json',
            success: function(response) {
                var msg = 'Your <a href=/projects/"' + data["name"] + '">project</a> has been created.';
                $('#apply-response .message-body').html(msg);
                $('#apply-response').removeClass('is-danger').addClass('is-success').removeClass('is-hidden');
                $('#apply-button').removeClass('is-loading');
            },
            error: function(response) {
                var msg;
                if (response.responseJSON) { msg = response.responseJSON["error"]; }
                else { msg = response.responseText; }
                $('#apply-response .message-body').html(msg);
                $('#apply-response').removeClass('is-success').addClass('is-danger').removeClass('is-hidden');
                $('#apply-button').removeClass('is-loading');
            }
        });
        return false;
    });
}
