package dataprovider;

import java.io.FileReader;
import java.io.IOException;

import org.json.simple.JSONArray;
import org.json.simple.JSONObject;
import org.json.simple.parser.JSONParser;
import org.json.simple.parser.ParseException;
import org.testng.annotations.Test;

public class Dataprovider_Json { 
	  
	public String email , password ; 

	
    public void  jsonDataReader() throws IOException, ParseException
    {     
    	
    	  
		FileReader reader = new FileReader("E:\\ITI\\test Automation\\java-2020-12eclipse\\LevelsetAutomation3\\src\\test\\java\\dataprovider\\data.json");
             
        //   create object from json 
		JSONParser jsonParser = new JSONParser();
	    // create jsonarray to  put values in and can loop in it .
		      Object obj = jsonParser.parse(reader);
		      JSONArray dataReaderArray = new JSONArray() ; 
		             dataReaderArray = (JSONArray) obj ;
	//	      org.json.simple.JSONArray jsonArray= (org.json.simple.JSONArray) jsonParser.parse(reader);

	     // loop for all the array  and put data in object of type Object
		 // i put in object because i can not convert jsonarray to jsonobject
		// to put in object than cast it to jsonobject 
		 for ( Object  object : dataReaderArray ) {  
			   // create jsonobject and use to get values
			 JSONObject jsonobj  = new JSONObject() ; 
			    jsonobj = (JSONObject) object  ;  
			    
			  email =(String) jsonobj.get("email"); 
			 password = (String) jsonobj.get("password")  ; 
			 System.out.println(email) ;
		 }
		
	     }
		
  
  
}
