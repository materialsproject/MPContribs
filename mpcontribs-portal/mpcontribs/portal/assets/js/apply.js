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
        data["owner"] = $("#owner").val();
        data["references"] = [
            {"label": data["ref_label"], "url": data["ref_url"]}
        ]
        delete data["ref_label"];
        delete data["ref_url"];
        $.post({
            url: window.api['host'] + 'projects/',
            headers: window.api['headers'],
            data: JSON.stringify(data),
            dataType: "json", contentType: 'application/json',
            success: function(response) {
                var msg = `Thank you for submitting your project application. Please check your
                inbox (and spam) for an e-mail asking you to subscribe for MPContribs
                notifications. Once your e-mail address is confirmed we will notify you if/when
                your project has been accepted for dissemination.`;
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
