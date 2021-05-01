package dataprovider;


import java.io.BufferedReader;
import java.io.FileNotFoundException;
import java.io.FileReader;
import java.io.IOException;
import java.util.Properties;
public class DataProvider { 
        
	   BufferedReader reader;    
	   String propertyFilePath = "configs\\config.properties";  // file path 
	public Properties ConfigFileReader(){
		 
		try {   
		// BufferedReader class create a reader who read text from character - input stream   
	// FileReader class Creates a new {@code FileReader}, given the name of the file to read,
		   reader = new BufferedReader(new FileReader(propertyFilePath));
		   
		   Properties properties = new Properties();
		   try { 
	   // object from type properties to load file 
		   properties.load(reader);
		  //  reader.close();
		   return properties ;
		   } catch (IOException e) {
		   e.printStackTrace();
		   }
		   } catch (FileNotFoundException e) {
		   e.printStackTrace();
		   throw new RuntimeException("Configuration.properties not found at " + propertyFilePath);
		   }
		return null; 
		   }
}
