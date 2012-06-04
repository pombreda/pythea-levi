function initialize() {
    $('#content form').submit( function(event, ui) { 
        event.preventDefault();
        var url = event.currentTarget.action;
        var url = event.currentTarget.attributes.action.nodeValue;
        data = $(this).serialize();
        $.address.value(url + '?' + data); 
    });
    $(".witness" ).draggable({
        appendTo: "body",
        helper: "clone"
    });
    $("#content input").droppable({
        activeClass: "ui-state-default",
        hoverClass: "ui-state-hover",
        accept: ":not(.ui-sortable-helper)",
        drop: function( event, ui ) {
            var index = ui.draggable[0].href.split('/').pop();
            event.target.value=index;
        }
    });

    $('.variants-collapsible').hide();
    $('.variants-collapse').collapser({
        target: 'next',
        effect: 'slide', 
        changeText: 0,
        expandClass: 'expIco',
        collapseClass: 'collIco'
    });
    $(".witness-id").droppable({
	activeClass: "ui-state-default",
	hoverClass: "ui-state-hover",
	accept: ":not(.ui-sortable-helper)", 
	drop: function( event, ui ) {
            var index1 = ui.draggable[0].href.split('/').pop();
            var index2 = $(this).find('input').val();
            if ($(this).hasClass('a')) {
                index3 = $('#hidden-witness-id-b').val();
                var compare = index1 + "/" + index3;
            } else if ($(this).hasClass('b')) {
                index3 = $('#hidden-witness-id-a').val();
                var compare = index3 + "/" + index1;
            } else {
                var compare = index2 + "/" + index1;
            }
            $.address.value("compare/" + compare);
        }
    });
    $('.collapser').collapser({
        target: 'next',
        effect: 'slide', 
        changeText: 0,
        expandClass: 'expIco',
        collapseClass: 'collIco'
    });
}
$(document).ready(function(){
    initialize();
    $('body a').live('click', function( event, ui ) {
        event.preventDefault();
        var url = event.currentTarget.pathname;
        $.address.value(url);
    });
    $('.widget h4').collapser({
        target: 'next',
        effect: 'slide', 
        changeText: 0,
        expandClass: 'expIco',
        collapseClass: 'collIco'
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
            url: event.path,
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
    $("#selection ul").droppable({
	activeClass: "ui-state-default",
	hoverClass: "ui-state-hover",
	accept: ":not(.ui-sortable-helper,#selection a)", 
	drop: function( event, ui ) {
            var index = ui.draggable[0].href.split('/').pop();
            //var index = ui.href.split('/').pop();
            $.post("select", {id: index},
                   function( data ) { 
                       document.body.style.cursor = "default";
                       $("#selection ul").empty().append( data );
                       $(".witness").draggable({
                              appendTo: "body",
		              helper: "clone"
	               }); 
                   }   
            );
        }
    })
    $("#trash").droppable({
	activeClass: "ui-state-default",
	hoverClass: "ui-state-hover",
	accept: "#selection a", 
	drop: function( event, ui ) {
            var index = ui.draggable[0].href.split('/').pop();
            //var index = ui.href.split('/').pop();
            $.post("unselect", {id: index},
                   function( data ) { 
                       document.body.style.cursor = "default";
                       $("#selection ul").empty().append( data );
                       $(".witness").draggable({
                              appendTo: "body",
		              helper: "clone"
	               }); 
                   }   
            );
        }
    })
    $("#selection-form").submit( function( event, ui ) {
         event.preventDefault();
         var list = $("#selection").find("a").map( function() {
             return this.href.split('/').pop();
         });
         var tag = $('[name=tag-name]').val()
         list = jQuery.makeArray(list);
         $.post("tag", { 'tag': tag, 'ids[]': list} ); /* needs the [] to make an array */
             return false;
    });
    $("#search-form").submit( function( event, ui ) {
        event.preventDefault();
        var url = event.currentTarget.action;
        var criteria = $('#search-form').find('input[name="criteria"]').val()
        document.body.style.cursor = "wait";

        /* Send the data using post and put the results in a div */
        $.post( url, { criteria: criteria },
                function( data ) {
                   document.body.style.cursor = "default";
                   $("#search-results").empty().append( data );
                   $(".witness" ).draggable({
                       appendTo: "body",
                       helper: "clone"
                   });
                }
        );
        return false;
    });
});
