var template = /<!--Template:(.*)-->/

function loadIn(tag, html) {
    $(tag).empty().append(html);
    template_name = "";
    match = html.match(template);
    if( match ) { template_name = match[1] };
    initialize();
}

function initialize() {
    $('#content form').submit( function(event, ui) { 
        event.preventDefault();
        /*var url = event.currentTarget.action;*/
        var url = event.currentTarget.attributes.action.nodeValue;
        data = $(this).serialize();
        document.body.style.cursor = "wait";
        $.ajax({
            type: "POST",
            url: url,
            data: data,
            success: function(html, jqXHR) {
                loadIn('#content', html);
                document.body.style.cursor = "default";
            },
            error: function(jqXHR, textStatus, errorThrown) {
                $('#content').empty().append(textStatus + ' ' + jqXHR.responseText);
                document.body.style.cursor = "default";
            }
        });
    });
}

$(document).ready(function(){
    initialize();
    $('body a').live('click', function( event, ui ) {
        event.preventDefault();
        var url = event.currentTarget.pathname;
        var search = event.currentTarget.search;
        $.address.value(url + search);
    });
    $.address.change(function(event){
        if(event.path == '/') return;
        document.body.style.cursor = "wait";
        if($.isEmptyObject(event.parameters)) {
            type = "GET";
        } else {
            type = "POST";
        }
        $.ajax({
            type: type,
            url: event.value,
            data: event.parameters,
            success: function(html, textStatus, jqXHR) {
                loadIn('#content', html);
                document.body.style.cursor = "default";
            },
            error: function(jqXHR, textStatus, errorThrown) {
                $('#content').empty().append(textStatus + ' ' + jqXHR.responseText);
                initialize();
                document.body.style.cursor = "default";
            }
        });
    });
});
