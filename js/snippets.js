// Function to serialize collapsible state
    }, function( obj ) { 
            s = ''
            $('.variants-collapsible').each( function(index, value) {
                if($(this).is(':visible'))
                    s = '1' + s 
                else
                    s = '0' + s 
            }); 
            hex = ''
            for( i = s.length; i > 0; i = i -32) {
                s2 = s.substring(i-32,i);
                n = parseInt(s2,2)
                s3 = n.toString(16)
                while (s3.length < 4) s3 = '0' + s3; 
                hex = s3 + hex 
            }   
            n2 = parseInt(hex,16);
            bin = n2.toString(2);
            url = $.address.value();
//            url += '&state='+hex;
//            $.adress.autoUpdate(false);
//            $.address.value(url);
//            $.adress.autoUpdate(true);
    
    }); 

