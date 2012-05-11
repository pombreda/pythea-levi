function initialize() {
    $('#content form').submit( function(event, ui) { 
        event.preventDefault();
        var url = event.currentTarget.action;
        var url = event.currentTarget.attributes.action.nodeValue;
/*
        data = $(this).serialize();
        $.address.value(url + '?' + data); 
*/
        data = $(this).serialize();
        document.body.style.cursor = "wait";
        $.ajax({
            type: "POST",
//            url: event.path,
            url: url,
            data: data,
            success: function(html) {
                $('#content').empty().append(html);
                initialize();
                document.body.style.cursor = "default";
            },
            error: function(jqXHR, textStatus, errorThrown) {
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
//            url: event.path,
            url: event.value,
            data: event.parameters,
            success: function(html) {
                $('#content').empty().append(html);
                initialize();
                document.body.style.cursor = "default";
            },
            error: function(jqXHR, textStatus, errorThrown) {
                document.body.style.cursor = "default";
            }
        });
    });
});
