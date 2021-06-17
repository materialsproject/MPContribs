function prep_download(query) {
    const url = "/contributions/download/create";
    const project = query["project"];
    $.get({
        contentType: "json", dataType: "json", url: url, data: query
    }).done(function(response) {
        if ("error" in response) {
            alert(response["error"]);
        } else if (response["progress"] < 1) {
            const progress = (response["progress"] * 100).toFixed(0);
            $("#download_" + project + "_progress").text(progress + "%");
            prep_download(query);
        } else {
            const href = "/contributions/download/get?" + $.param(query);
            const fmt = query["format"];
            const prefix = "#download_" + project + "_";
            $("#get_download_" + project).attr("href", href).removeClass("is-hidden");
            $(prefix + fmt).removeClass('is-loading').addClass("is-hidden");
            $(prefix + "progress").addClass("is-hidden");
        }
    });
}

$(document).ready(function () {
    var li = $('#browse-toggle').parent();
    li.siblings().removeClass('is-active');
    li.addClass('is-active');

    var imageNames = require.context('../images/', false, /\.(png)$/).keys();

    $.each(imageNames, function(idx, name) {
        var imageName = name.replace('./', '');
        import('../images/' + imageName).then(function(src) {
            var suffix = imageName.replace('.png', '_img');
            $('[name=thumbnail_' + suffix + ']').each(function(idx) {
                var img = $("<img/>", {src: src.default, width: "100%"});
                $(this).append(img);
            });
        }).catch(function(err) { console.log(err); });
    });

    $('[name=thumbnail]').on('click', function(e) {
        e.preventDefault();
        var selector = '#' + $(this).attr("id") + "_modal";
        window.scrollTo(0, 0);
        $(selector).addClass("is-active");
        $("html").addClass("is-clipped");
    });

    $('[name=thumbnail_close]').on('click', function(e) {
        e.preventDefault();
        $(this).parent().removeClass("is-active");
        $('html').removeClass("is-clipped");
    });

    $('a[name="download"]').click(function(e) {
        const project = $(this).data('project');
        const fmt = $(this).data('format');
        var hide_id = "#download_" + project;
        if (fmt === "json") { hide_id += "_csv" } else { hide_id += "_json"; }
        $(hide_id).addClass("is-hidden");
        $(this).addClass('is-loading');
        $("#download_" + project + "_progress").text("0%").removeClass("is-hidden");
        var download_query = {
            "format": fmt, "project": project,
            "include": "structures,tables,attachments"
        };
        prep_download(download_query);
    });

    $('a[name="get_download"]').click(function() {
        const project = $(this).data('project');
        const prefix = "#download_" + project + "_";
        $(prefix + "json").removeClass("is-hidden");
        $(prefix + "csv").removeClass("is-hidden");
        $(prefix + "progress").addClass("is-hidden");
        $(this).addClass("is-hidden");
    });
});
